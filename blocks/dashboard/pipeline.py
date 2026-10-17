"""Визуальный индикатор трёх этапов обработки заявки.

Плашки: 📄 Рендер документов, ✅ Согласование, 📤 Отправка на Диск.
Текущий этап подсвечивается цветом, прошедшие — зелёным, будущие — серым.

Используется в app_view (страница заявки). Тонкая обёртка для вынесения
логики из page.py:2330 — точка расширения для будущих этапов.
"""
import json

from blocks.dashboard import page as _page


def pipeline_visual(app_id: int) -> str:
    """HTML с тремя плашками этапов обработки.

    Возвращает строку, в которой 3 блока со статусами:
    - done (зелёный) — этап пройден
    - active (синий) — сейчас идёт
    - failed (красный) — была ошибка
    - pending (серый) — ещё не наступил
    """
    state = _page.now_state(app_id) or {}
    q_state = _page._queue_state(app_id)
    last_run = _page._last_run(app_id) or {}
    docs = _page.db.application_doc_summary(app_id) or {}

    total = int(docs.get("total") or 0)
    done = int(docs.get("filled") or 0) + int(docs.get("verified") or 0) + int(docs.get("sent") or 0)
    verified = int(docs.get("verified") or 0) + int(docs.get("sent") or 0)
    rejected = int(docs.get("rejected") or 0)
    sent = int(docs.get("sent") or 0)

    errs = _page._err_list(last_run) if last_run else []
    has_error = bool(errs)

    # 1. РЕНДЕР: pending → active (если заявка в очереди/работает и есть pending) → done (все собрано)
    render_pct = (done * 100 // total) if total else 0
    if sent:
        render_state = "done"
    elif has_error:
        render_state = "failed"
    elif q_state == "running":
        render_state = "active"
    elif q_state == "queued":
        render_state = "pending"
    elif done >= total and total:
        render_state = "done"
    else:
        render_state = "active" if total else "pending"

    # 2. СОГЛАСОВАНИЕ: пока ни один документ не подтверждён → pending; есть подтверждения → active/done
    if sent:
        verify_state = "done"
    elif verified == 0 and done == 0:
        verify_state = "pending"
    elif verified >= total and total:
        verify_state = "done"
    elif has_error:
        verify_state = "failed"
    else:
        verify_state = "active"

    # 3. ОТПРАВКА: всё отправлено → done; есть ошибка → failed; иначе pending
    if sent:
        send_state = "done"
    elif has_error:
        send_state = "failed"
    elif verified >= total and total:
        send_state = "active"
    else:
        send_state = "pending"

    # Текущий шаг GDrive-отправки (send_folder / send_upload / send_upload_file /
    # send_upload_txt). Показываем прямо на плашке, чтобы админ видел прогресс.
    send_substep = ""
    try:
        from services import app_steps as _steps
        rows = _steps.trail(app_id, limit=8)
        for r in reversed(rows):
            step = r.get("step") or ""
            if step in ("send_folder", "send_upload", "send_upload_file", "send_upload_txt"):
                notes = {
                    "send_folder":    "📁 создаю папку заявки на Диске",
                    "send_upload":    "📤 загружаю PDF-документы",
                    "send_upload_file": "📎 файл «" + (r.get("note") or "")[:40] + "»",
                    "send_upload_txt": "📝 текст заявки (Telegram)",
                }
                send_substep = notes.get(step, step)
                break
    except Exception:
        pass

    palette = {
        "done":    ("✅", "#DCFCE7", "#15803D", "пройдено"),
        "active":  ("⏳", "#DBEAFE", "#1D4ED8", "в работе"),
        "failed":  ("⚠", "#FEE2E2", "#B91C1C", "ошибка"),
        "pending": ("○", "#F1F5F9", "#64748B", "ждёт"),
    }

    def chip(num: int, icon: str, title: str, sub: str, st: str, pct: int = -1) -> str:
        ico, bg, fg, st_lbl = palette[st]
        bar = ""
        if pct >= 0:
            bar = (f'<div style="margin-top:6px;height:4px;border-radius:2px;'
                   f'background:#E2E8F0;overflow:hidden">'
                   f'<div style="width:{pct}%;height:100%;background:{fg};"></div></div>')
        return (f'<div class="pv-chip pv-{st}" style="flex:1;min-width:0;padding:12px;'
                f'border-radius:8px;background:{bg};color:{fg};'
                f'border:1px solid {fg}22;font-size:12.5px">'
                f'<div style="display:flex;align-items:center;gap:6px">'
                f'<span style="font-size:18px;line-height:1">{ico}</span>'
                f'<span style="font-weight:700;font-size:13px">Этап {num}: {title}</span>'
                f'</div>'
                f'<div style="margin-top:4px;opacity:0.85">{sub} · {st_lbl}</div>'
                f'{bar}'
                f'</div>')

    r_sub = f"{done}/{total} документов" if total else "документов пока нет"
    v_sub = f"{verified}/{total} подтверждено" + (f" · {rejected} отклонено" if rejected else "")
    s_sub = send_substep or ("отправлено на Google Диск" if sent else ("ошибка отправки" if has_error and verified >= total else "ожидает согласования всех документов"))

    html = (
        '<div class="pipeline-visual" id="pipeline-visual" '
        'style="display:flex;gap:8px;margin:10px 0;flex-wrap:wrap">'
        + chip(1, "📄", "Рендер документов", r_sub, render_state, render_pct)
        + chip(2, "✅", "Согласование", v_sub, verify_state)
        + chip(3, "📤", "Отправка на Диск", s_sub, send_state)
        + '</div>'
    )
    return html