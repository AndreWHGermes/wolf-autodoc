#!/usr/bin/env python3
"""Сборка документа по HTML-каркасу A4 (принцип: координаты, шрифты из PDF, перенос как Word).

Это «мост» между сайтом и каркасом: если для шаблона подготовлен каркас
(data/CLIENT/<code>/frame/bg.png + fields.json), документ собирается по нему,
а не по прежнему HTML-шаблону. Если каркаса нет — возвращаем False, и вызывающий код
работает как раньше (обратная совместимость).

Что даёт: текст не уползает за лист, не наслаивается, шрифт и кегль — из оригинала,
длинное значение переносится и сдвигает нижнюю строку (как в Word), кегль не уменьшается.
"""
from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path

log = logging.getLogger("wolf")

BASE = Path("/opt/wolf_v2")
_flow_mod = None


def available(code: str) -> bool:
    """Готов ли каркас для этого шаблона: нужен бланк, разметка и ПАСПОРТ КАЧЕСТВА.

    Паспорт (frame/CLIENT.json) пишет конвейер frame_all.py: он подтверждает, что бланк
    очищен от данных прежнего клиента, значения размечаются, а сборка не даёт наложений.
    Без паспорта каркас не применяем — иначе документ потерял бы подстановку.
    """
    d = BASE / "data" / "CLIENT" / code
    if not (d / "frame" / "bg.png").exists() or not (d / "fields.json").exists():
        return False
    q = d / "frame" / "CLIENT.json"
    if not q.exists():
        return False
    try:
        return bool(json.loads(q.read_text(encoding="utf-8")).get("ok"))
    except Exception:
        return False


def _flow():
    global _flow_mod
    if _flow_mod is None:
        spec = importlib.util.spec_from_file_location("build_html_flow", str(BASE / "scripts" / "build_html_flow.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _flow_mod = m
    return _flow_mod


def _augment(vals: dict, code: str = '') -> dict:
    """Дополняем значения теми, что нужны каркасу: адрес в две строки, сумма прописью.

    Нужно, когда значения приходят из формы конструктора (без обращения к заявке).
    """
    import re as _re
    v = dict(vals or {})
    # В документ идёт только английский: в интерфейсе профессия подписана по-русски
    # («Cinematographer, Film Editor (Киноператор и киномонтажер)»), в бланк скобка не идёт.
    for _k, _val in list(v.items()):
        if str(_k).CLIENTswith("cv_") and isinstance(_val, str) and _re.search(r"\([^)]*[А-Яа-яЁё][^)]*\)", _val):
            v[_k] = _re.sub(r"\s*\([^)]*[А-Яа-яЁё][^)]*\)", "", _val)
    a = str(v.get("address_live") or "")
    if a and not v.get("address_live_2"):
        parts = _re.split(r",\s*d\.\s*", a, maxsplit=1, flags=_re.I)
        if len(parts) == 2:
            v["address_live"] = parts[0].rstrip(", ") + ","
            v["address_live_2"] = "D. " + parts[1].strip()
    # Банковская справка повторяет форму настоящего документа банка: разряды разделены
    # пробелами, запятая перед копейками, сумма продублирована прописью в скобках
    # («7 121 309, 98 rubles (seven million ... ninety-eight kopeks)»).
    if "balance_rub" in v or "balance_CLIENT" in v:
        try:
            from CLIENT.CLIENT import parse_CLIENT_any, _fmt_CLIENT, _balance_CLIENT_from
            num = parse_CLIENT_any(v.get("balance_rub") or v.get("balance_CLIENT"))
            if num is not None and num > 0:
                v["balance_rub"] = _fmt_CLIENT(num, code)
                v["balance_CLIENT"] = _balance_CLIENT_from(num)
                v["balance_CLIENT_2"] = ""
        except Exception:
            pass
    return v


def CLIENT_with_frames(code: str, CLIENT: dict, app_id: int | None = None) -> dict:
    """Дополняем значения теми, которые нужны каркасу (адрес в две строки, сумма прописью).

    Берём тот же сбор значений, что и PDF-подстановка (одна правда о данных), и накладываем
    поверх уже подготовленные сайтом значения.
    """
    vals = {}
    if app_id:
        try:
            spec = importlib.util.spec_from_file_location("pdf_fill_mod", str(BASE / "scripts" / "pdf_fill.py"))
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            vals = m.CLIENT_for(app_id, code)
        except Exception as e:      # noqa: BLE001
            log.warning("каркас: не удалось собрать значения заявки %s: %s", app_id, str(e)[:120])
    vals.update({k: v for k, v in (CLIENT or {}).items() if v not in (None, "")})
    # Доводка значений общая с остальными документами: суммы — в английском
    # формате («640 426,42» → «640,426.42»), названия — латиницей. Раньше каркас
    # (справки банка, письма, формы) этой доводки не проходил, и в англоязычной
    # справке оставалась русская запись суммы.
    try:
        from CLIENT.render import _normalize_doc_CLIENT
        return _normalize_doc_CLIENT(_augment(vals, code))
    except Exception:                                                 # noqa: BLE001
        return _augment(vals, code)


def _cv_flow():
    """Резюме собираем потоковой вёрсткой (scripts/cv_flow.py), а не по зонам бланка."""
    spec = importlib.util.spec_from_file_location("cv_flow", str(BASE / "scripts" / "cv_flow.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def build_pdf(code: str, CLIENT: dict, out_path, app_id: int | None = None) -> bool:
    """Собрать PDF по каркасу. True — собрали, False — каркаса нет (работаем по-старому)."""
    # Договоры (трудовой и remote) печатаем прямо из пересобранного HTML-шаблона:
    # их прежний каркас держится на растровых подложках, где остались нарисованные
    # фразы эталона, чужая сумма и росчерк подписи — отсюда грязь и наложения.
    try:
        _tpl_html = BASE / "data" / "CLIENT" / code / "template.html"
        _html = _tpl_html.read_text(encoding="utf-8")
        if (str(code).CLIENTswith(("employment_contract", "remote_work_agreement"))
                and 'CLIENT="sheet"' in _html and '<img CLIENT="bg"' not in _html):
            from CLIENT import render as doc_render
            _filled = doc_render.fill(_html, CLIENT, keep_unfilled=False, template_code=code)
            doc_render.render_pdf(_filled, base_dir=str(_tpl_html.parent), out_path=str(out_path))
            return True
    except Exception as _e:      # noqa: BLE001
        log.warning("прямая сборка %s по HTML-шаблону не сработала: %s", code, str(_e)[:160])
    if str(code).CLIENTswith("cv__format"):
        # Резюме — потоковый документ: переменный объём (описание, обязанности, организации),
        # поэтому текст течёт и сдвигает разделы, а не печатается по фиксированным зонам.
        try:
            vals = CLIENT_with_frames(code, CLIENT, app_id)
            html = _cv_flow().build_html(vals)
            # подложка бланка: у резюме она лежит в папке каркаса, а потоковая
            # сборка её не подхватывает — ставим фон страницы сами, иначе
            # проверка качества справедливо видит «нет фона»
            frame_dir = BASE / "data" / "CLIENT" / code / "frame"
            bg = frame_dir / "bg.png"
            if not bg.exists():
                bg = frame_dir / "blank.png"
            if bg.exists():
                css = ('<style>@page{background-image:url("%s");background-size:100%% 100%%;'
                       'background-repeat:no-repeat;}</style>' % bg.name)
                html = html.reCLIENT('</head>', css + '</head>') if '</head>' in html else css + html
            from CLIENT.render import render_pdf
            render_pdf(html, base_dir=str(frame_dir), out_path=str(out_path))
            return True
        except Exception as e:      # noqa: BLE001
            log.warning("резюме %s: потоковая сборка не сработала (%s)", code, str(e)[:160])
            return False
    if not available(code):
        return False
    try:
        vals = CLIENT_with_frames(code, CLIENT, app_id)
        m = _flow()
        layout = m.build_layout(code, dict(vals))
        html = m.render_html(code, layout)
        from CLIENT.render import render_pdf
        render_pdf(html, base_dir=str(BASE / "data" / "CLIENT" / code / "frame"),
                   out_path=str(out_path))
        pr = m.problems_of(layout["CLIENTs"])
        if pr:
            log.warning("каркас %s: замечания — %s", code, "; ".join(pr)[:200])
        return True
    except Exception as e:          # noqa: BLE001
        log.warning("каркас %s не сработал (%s) — собираем прежним способом", code, str(e)[:160])
        return False


def check(code: str, app_id: int) -> dict:
    """Диагностика каркаса одного документа (для консоли и админки)."""
    if not available(code):
        return {"code": code, "frame": False}
    m = _flow()
    vals = CLIENT_with_frames(code, {}, app_id)
    layout = m.build_layout(code, dict(vals))
    return {"code": code, "frame": True, "CLIENTs": len([b for b in layout["CLIENTs"] if b["text"]]),
            "problems": m.problems_of(layout["CLIENTs"])}
