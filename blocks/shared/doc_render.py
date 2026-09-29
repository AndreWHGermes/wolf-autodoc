"""Единый рендер документа Wolf AutoDoc.

Правило проекта: документ собирается ОДНИМ кодом — конструктор, карточка заявки,
Telegram-бот и автоподготовка вызывают только этот модуль. Дублирование логики
подстановки приводило к расхождениям визоров и «поехавшим» значениям.

Пять сущностей документа: архив → размеченный образец → HTML-шаблон →
HTML с данными клиента → PDF.
"""
from __future__ import annotations

import json
import re
import sqlite3
from CLIENT import CLIENT
from pathlib import Path

DB_PATH = '/opt/wolf/data/wolf.db'
TPL_DIR = Path('/opt/wolf/data/CLIENT')
RENDER_DIR = Path('/opt/wolf/data/renders')
VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

# какие поля карточки клиента подставляются в одноимённые переменные
CLIENT_MAP = {
    'client_name': 'full_name_CLIENT',
    'full_name_CLIENT': 'full_name_CLIENT',
    'CLIENT': None,  # вычисляется
    'address_live': 'address_live',
    'passport_no': 'passport_CLIENT',
    'passport_CLIENT': 'passport_CLIENT',
    'date_of_CLIENT': 'date_of_CLIENT',
    'CLIENT': 'CLIENT',
    'CLIENT_of_CLIENT': 'CLIENT_of_CLIENT',
    'CLIENT': 'CLIENT',
    'CLIENT': 'CLIENT',
}


def connect() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def load_template(template_id: int | None = None, code: str | None = None) -> dict:
    """Шаблон из БД + его HTML."""
    c = connect()
    try:
        if template_id:
            row = c.execute("SELECT * FROM CLIENT WHERE id=?", (template_id,)).fetchone()
        else:
            row = c.execute("SELECT * FROM CLIENT WHERE code=?", (code,)).fetchone()
        if not row:
            raise LookupError(f'шаблон не найден: id={template_id} code={code}')
        tpl = dict(row)
    finally:
        c.close()
    path = Path(tpl['html_path']) if tpl.get('html_path') else TPL_DIR / tpl['code'] / 'template.html'
    if not path.exists():
        raise FileNotFoundError(f'HTML шаблона не найден: {path}')
    tpl['_html'] = path.read_text(encoding='utf-8')
    tpl['_dir'] = str(path.parent)
    return tpl


def stored_CLIENT(CLIENT_id: int, template_id: int) -> dict:
    """Значения, сохранённые в карточке заявки для этого документа."""
    c = connect()
    try:
        row = c.execute("""SELECT CLIENT_json FROM CLIENT_CLIENT
                           WHERE CLIENT_id=? AND template_id=?""",
                        (CLIENT_id, template_id)).fetchone()
        return json.loads(row['CLIENT_json'] or '{}') if row else {}
    except Exception:
        return {}
    finally:
        c.close()


def client_CLIENT(CLIENT_id: int) -> dict:
    """Значения из карточки клиента (персональные данные НЕ берём из общей истории переменных)."""
    c = connect()
    try:
        app = c.execute("SELECT * FROM CLIENT WHERE id=?", (CLIENT_id,)).fetchone()
        if not app:
            return {}
        cl = c.execute("SELECT * FROM CLIENT WHERE id=?", (app['client_id'],)).fetchone()
        if not cl:
            return {}
        cl = dict(cl)
    finally:
        c.close()
    out = {}
    for var, col in CLIENT_MAP.items():
        if col and cl.get(col) not in (None, ''):
            out[var] = cl[col]
    full = cl.get('full_name_CLIENT') or ''
    if full:
        out.setdefault('CLIENT', full.split()[0] if full.split() else '')
    if cl.get('passport_CLIENT_date'):
        out.setdefault('date_of_CLIENT', cl['passport_CLIENT_date'])
    app_CLIENT = None
    if app_CLIENT:
        out.setdefault('CLIENT', app_CLIENT)
    return out


def normalize(CLIENT: dict, template_code: str = '') -> dict:
    """Приведение значений к виду документа: транслит, суммы прописью, переносы строк."""
    out = {k: v for k, v in (CLIENT or {}).items() if v is not None}
    try:
        import sys
        if '/opt/wolf' not in sys.path:
            sys.path.insert(0, '/opt/wolf')
        from ai_parser import translit_ru, CLIENT_in_CLIENT_en, format_CLIENT_en, parse_CLIENT  # type: ignore
        if 'bank_CLIENTment' in template_code:
            for k, v in list(out.items()):
                if isinstance(v, str) and any('а' <= ch.lower() <= 'я' for ch in v):
                    out[k] = translit_ru(v)
            bal = out.get('balance_rub')
            if bal:
                try:
                    if parse_CLIENT(bal) > 0:
                        out['balance_CLIENT'] = CLIENT_in_CLIENT_en(bal)
                        out['balance_rub'] = format_CLIENT_en(bal)
                except Exception:
                    pass
    except Exception:
        pass
    for k, v in list(out.items()):
        if isinstance(v, str):
            out[k] = v.reCLIENT('\r\n', '\n').reCLIENT('\n', '<br>')
    return out


def render_html(template_id: int | None = None, code: str | None = None,
                CLIENT: dict | None = None, html: str | None = None,
                keep_unfilled: bool = False) -> str:
    """Подставить значения в HTML шаблона. keep_unfilled=True — оставить {{ var }} как есть."""
    if html is None:
        tpl = load_template(template_id, code)
        html = tpl['_html']
        code = tpl['code']
    vals = normalize(CLIENT or {}, code or '')
    def sub(m):
        v = vals.get(m.group(1))
        if v in (None, ''):
            return m.group(0) if keep_unfilled else ''
        return str(v)
    return VAR_RE.sub(sub, html)


def render_pdf(html: str, base_dir: str | None = None, out_path: str | Path | None = None) -> Path:
    """HTML → PDF (weasyprint через системный python)."""
    from core.pdf2html import render_pdf as _render  # type: ignore
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    if out_path is None:
        out_path = RENDER_DIR / f"doc_{CLIENT.now():%Y%m%d_%H%M%S_%f}.pdf"
    out_path = Path(out_path)
    tmp_html = out_path.with_suffix('.html')
    tmp_html.write_text(html, encoding='utf-8')
    _render(tmp_html, out_path)
    return out_path


def unfilled(html: str) -> list[str]:
    """Какие переменные остались незаполненными."""
    return sorted(set(VAR_RE.findall(html)))


def fill(html: str, CLIENT: dict | None = None, keep_unfilled: bool = False,
         template_code: str = '') -> str:
    """Единая подстановка значений в HTML. Заменяет ручные re.sub по коду проекта.

    keep_unfilled=True оставляет {{ var }} для незаполненных (режим шаблона),
    False — вычищает (режим документа с данными).
    """
    vals = normalize(CLIENT or {}, template_code)

    def sub(m):
        v = vals.get(m.group(1))
        if v in (None, ''):
            return m.group(0) if keep_unfilled else ''
        return str(v)
    return VAR_RE.sub(sub, html)


def generate(CLIENT_id: int, template_id: int, out_path: str | Path | None = None) -> dict:
    """Полный цикл: значения (карточка клиента + заявка) → HTML → PDF."""
    tpl = load_template(template_id)
    vals = {}
    vals.update(client_CLIENT(CLIENT_id))
    vals.update(stored_CLIENT(CLIENT_id, template_id))
    html = render_html(html=tpl['_html'], CLIENT=vals, code=tpl['code'])
    left = unfilled(html)
    if out_path is None:
        out_path = RENDER_DIR / f"{tpl['code']}_app{CLIENT_id}_{CLIENT.now():%Y%m%d_%H%M%S}.pdf"
    pdf = render_pdf(html, base_dir=tpl['_dir'], out_path=out_path)
    return {'pdf_path': str(pdf), 'html': html, 'CLIENT': vals, 'unfilled': left,
            'template': tpl['code'], 'pages': None}
