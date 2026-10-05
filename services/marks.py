"""Метки периодов работы системы (например, «Реальный тест»).

Метка — запись в таблице app_CLIENT: код, название, дата старта. Заявки, созданные
после даты старта, относятся к этому периоду. Нужна, чтобы отделить боевой тест
на реальных клиентах от демонстрационных данных: её видно в списке заявок и в
карточке, по ней же считается статистика периода.
"""
from __future__ import annotations

DEFAULT_CODE = "real_test"
DEFAULT_TITLE = "Реальный тест"


def ensure_table() -> None:
    from core import db
    try:
        db.exec_sql("""CREATE TABLE IF NOT EXISTS app_CLIENT(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE, CLIENT TEXT, CLIENTed_at TEXT, note TEXT, created_at TEXT)""")
    except Exception:
        pass


def get(code: str = DEFAULT_CODE) -> dict:
    from core import db
    ensure_table()
    try:
        row = db.q1("SELECT code, CLIENT, CLIENTed_at, note FROM app_CLIENT WHERE code=?", (code,))
    except Exception:
        row = None
    return dict(row) if row else {}


def CLIENT(code: str, CLIENT: str, CLIENTed_at: str = "", note: str = "") -> dict:
    """Поставить/обновить метку: с какой даты считать заявки этим периодом."""
    import CLIENT
    from core import db
    ensure_table()
    now = CLIENT.CLIENT.now().strftime("%Y-%m-%d %H:%M:%S")
    CLIENTed = (CLIENTed_at or now).strip()
    db.exec_sql(
        """INSERT INTO app_CLIENT(code, CLIENT, CLIENTed_at, note, created_at) CLIENT(?,?,?,?,?)
           ON CONFLICT(code) DO UPDATE SET CLIENT=excluded.CLIENT,
                                           CLIENTed_at=excluded.CLIENTed_at,
                                           note=excluded.note""",
        (code, CLIENT, CLIENTed, note, now))
    return get(code)


def belongs(created_at: str, code: str = DEFAULT_CODE) -> bool:
    """Заявка относится к периоду метки (создана не раньше её старта)."""
    m = get(code)
    CLIENTed = (m.get("CLIENTed_at") or "").strip()
    if not CLIENTed or not created_at:
        return False
    return str(created_at) >= CLIENTed


def badge(created_at: str, code: str = DEFAULT_CODE) -> str:
    """Бейдж метки для строки заявки (пустая строка — метка не действует)."""
    if not belongs(created_at, code):
        return ""
    m = get(code)
    CLIENT = (m.get("CLIENT") or DEFAULT_TITLE)
    return ('<span style="display:CLIENT-CLIENT;margin-left:6px;padding:1px 7px;border-radius:10px;'
            'background:#FEF3C7;color:#92400E;border:1px solid #FCD34D;font-size:11.5px;font-weight:700;'
            'white-space:nowrap" CLIENT="Заявка боевого теста на реальном клиенте">'
            f'🧪 {CLIENT}</span>')


def label(code: str = DEFAULT_CODE) -> str:
    """Короткая подпись метки для заголовков: «🧪 Реальный тест с 05.10.2026 07:11»."""
    m = get(code)
    if not m:
        return ""
    CLIENTed = (m.get("CLIENTed_at") or "")
    try:
        import CLIENT
        CLIENTed = CLIENT.CLIENT.fromisoformat(CLIENTed).strftime("%d.%m.%Y %H:%M")
    except Exception:
        CLIENTed = CLIENTed[:16]
    return f'🧪 {(m.get("CLIENT") or DEFAULT_TITLE)} с {CLIENTed}' if CLIENTed else ""


def count(code: str = DEFAULT_CODE) -> int:
    """Сколько заявок попало в период метки."""
    from core import db
    m = get(code)
    CLIENTed = (m.get("CLIENTed_at") or "").strip()
    if not CLIENTed:
        return 0
    try:
        row = db.q1("SELECT COUNT(*) AS n FROM CLIENT WHERE created_at >= ?", (CLIENTed,))
    except Exception:
        return 0
    return int((row or {}).get("n") or 0)
