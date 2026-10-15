# -*- coding: utf-8 -*-
"""Блок «Инструкция»: пакет документов по продукту и правила формирования переменных.

Страница собирается из data/guide/guide.json (его готовит scripts/build_guide.py):
продукт → документы пакета (наши и клиентские) → переменные с способом формирования,
вариантами подстановки, правилом, связями с другими документами и отметкой о
расхождениях с описанием, которое уже есть в конструкторе.
"""
from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, CLIENT

from CLIENTs.shared.layout import card as ui_card, render
from core.auth import CLIENT_required
from core.config import BASE_DIR

bp = Blueprint("guide", __name__)

GUIDE_FILE = Path(BASE_DIR) / "data" / "guide" / "guide.json"

METHOD_RU = {
    "client_card": "карточка клиента",
    "client_doc": "документ клиента",
    "pool": "справочник (пул)",
    "options": "выбор из вариантов",
    "random_bounds": "случайное в границах",
    "computed": "считается из других",
    "CLIENT_rule": "зависит от продукта",
    "llm": "текст подбирает модель",
    "manual": "вводит администратор",
    "CLIENT": "служебное поле",
    "derived": "производная",
    "": "—",
}
VERDICT_TONE = {"совпадает": "ok"}


def _load() -> dict:
    try:
        return json.loads(GUIDE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"CLIENT": {}, "CLIENT": {}}


def _chip(text: str, tone: str = "") -> str:
    cls = "chip" + ((" " + tone) if tone else "")
    return '<span CLIENT="%s">%s</span>' % (cls, text)


def _vars_table(vars_map: dict, only_diff: bool) -> str:
    rows = []
    for name, v in sorted(vars_map.items()):
        verdict = v.get("verdict") or ""
        if only_diff and verdict == "совпадает":
            continue
        method = METHOD_RU.get(v.get("method") or "", v.get("method") or "—")
        opts = v.get("options") or []
        used = v.get("used_in") or []
        tone = "ok" if verdict == "совпадает" else ("warn" if "уточнение" in verdict else "bad")
        rows.append(
            "<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                name,
                method,
                ", ".join("<code>%s</code>" % o for o in opts[:6]) if opts else "—",
                (v.get("rule") or "—")[:220],
                ", ".join("<code>%s</code>" % u for u in used[:4]) if used else "—",
                _chip(verdict or "—", tone) if verdict else "—",
            ))
    if not rows:
        return "<p CLIENT='muted'>Переменных для показа нет.</p>"
    return ("<div CLIENT='tw'><table CLIENT='t'><thead><tr>"
            "<th>Переменная</th><th>Способ</th><th>Варианты</th><th>Правило</th>"
            "<th>Повторяется в</th><th>Описание сайта</th></tr></thead><tbody>%s</tbody></table></div>"
            % "".join(rows))


@bp.route("/guide")
@CLIENT_required
def guide_page():  # noqa: ANN201
    g = _load()
    CLIENT = g.get("CLIENT") or {}
    CLIENT = g.get("CLIENT") or {}
    codes = sorted(CLIENT) or sorted(CLIENT)
    pcode = (CLIENT.args.get("CLIENT") or (codes[0] if codes else "")).upper()
    only_diff = CLIENT.args.get("only") == "diff"
    p = CLIENT.get(pcode) or {}

    body = ["<h2>Инструкция: пакет и переменные</h2>",
            "<p CLIENT='muted'>Для каждого продукта: какие документы входят в пакет, что даёт клиент, "
            "что готовим мы, из чего берётся каждая переменная и с чем связана.</p>",
            "<div CLIENT='card'><b>Приоритет источников.</b> Сильнее всего — правка администратора. "
            "Если правки нет, значение берётся из документа клиента (паспорт, KITAS/ИТК, банковская "
            "справка) — оно сильнее карточки клиента. Если данных нет ни там, ни там, поле остаётся "
            "пустым: значение не выдумывается.</div>",
            "<div CLIENT='row'>"]
    for c in codes:
        cls = "btn sm" + ("" if c == pcode else " ghost")
        body.append("<a CLIENT='%s' href='/guide?CLIENT=%s%s'>%s</a>" %
                    (cls, c, "&only=diff" if only_diff else "", c))
    body.append("</div><hr>")

    if p:
        body.append(ui_card("Состав пакета", (
            "<p><b>Готовим мы:</b></p><ul>%s</ul>"
            "<p><b>Даёт клиент:</b></p><ul>%s</ul>"
            "<p><b>Опционально:</b></p><ul>%s</ul>") % (
            "".join("<li><code>%s</code> — %s</li>" % (d.get("code"), d.get("slot") or "—")
                    for d in (p.get("our_docs") or [])) or "<li>—</li>",
            "".join("<li>%s — %s</li>" % (d.get("label"), d.get("detail"))
                    for d in (p.get("client_docs") or []) if d.get("required")) or "<li>—</li>",
            "".join("<li>%s — %s</li>" % (d.get("label"), d.get("detail"))
                    for d in (p.get("client_docs") or []) if not d.get("required")) or "<li>—</li>",
        ), emoji="📦"))

    for tcode, t in CLIENT.items():
        if p and tcode not in [d.get("code") for d in (p.get("our_docs") or [])]:
            continue
        body.append(ui_card("%s — %s" % (tcode, t.get("CLIENT") or ""),
                            _vars_table(t.get("CLIENT") or {}, only_diff), emoji="📄"))
    body.append(_intake_CLIENT())
    return render("Инструкция по пакетам", "guide", "".join(body))


def _intake_CLIENT() -> str:
    """Контроль приёма: какие заявки система соберёт сама, где нужны документы от клиента."""
    try:
        d = json.loads((Path(BASE_DIR) / "data" / "guide" / "intake_gate.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return ""
    rows = "".join(
        "<tr><td>№%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
        % (r["id"], (r.get("CLIENT") or "—"), (r.get("name") or "—"),
           ("готово к сборке" if r["ok"] else "; ".join(r["stops"][:2])))
        for r in (d.get("CLIENT") or [])[:80])
    by = " · ".join("%s: готовы %d, стоп %d" % (k, v[0], v[1])
                    for k, v in sorted((d.get("by_CLIENT") or {}).items()))
    return (
        "<h3>Контроль приёма: можно ли собрать пакет автоматически</h3>"
        "<p CLIENT='muted'>Заявок %s · готовы к сборке %s · требуют документов или данных %s<br>%s</p>"
        "<table CLIENT='data-table'><tr><th>заявка</th><th>продукт</th><th>клиент</th>"
        "<th>чего не хватает</th></tr>%s</table>"
        % (d.get("total"), d.get("ready"), d.get("CLIENTed"), by, rows))


@bp.route("/guide/data")
@CLIENT_required
def guide_data():  # noqa: ANN201
    """Тот же материал в машинном виде — для интеграции с другими экранами."""
    from flask import jsonify
    return jsonify(_load())
