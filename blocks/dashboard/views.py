"""Отдельные рендереры HTML-блоков страницы заявки.

Сюда выносятся ЛОГИЧЕСКИ ЗАВЕРШЁННЫЕ блоки app_view. Каждый рендерер —
самостоятельная функция, возвращающая строку. Точка расширения: новые
блоки добавляются как новые функции, app_view просто вставляет их в
нужное место.

Безопасно: все функции получают готовый контекст (ctx_dict), не лезут в
БД сами — это всё ещё делает app_view.
"""
from blocks.dashboard import page as _page


def render_app_header(ctx) -> str:
    """Шапка карточки заявки: ID · клиент · статус · менеджер.

    ctx: dict с полями app_id, client, a, status_label, manager_btn.
    """
    app_id = ctx["app_id"]
    client = ctx["client"]
    a = ctx["a"]
    status_label = ctx["status_label"]
    manager_btn = ctx["manager_btn"]
    return (
        '<div class="app-head">\n'
        '  <div class="app-head-left">\n'
        f'    <span class="app-head-id">Заявка #{app_id}</span>\n'
        f'    <span class="app-head-client">· {_page.html.escape(_page.db.client_label(client) or "—")}</span>\n'
        f'    <span class="badge {_page.html.escape(status_label[1])}">{_page.html.escape(status_label[0])}</span>'
        f'{_page.kind_badge(a)}\n'
        '  </div>\n'
        '  <div class="app-head-right">\n'
        '    <span class="from-label">👤 Откуда:</span>\n'
        f'    {manager_btn}\n'
        '  </div>\n'
        '</div>\n'
    )


def render_comment_block(ctx) -> str:
    """Комментарий менеджера (если есть). ctx: _comment_html."""
    return ctx.get("_comment_html", "") or ""


def render_stages_intro(ctx) -> str:
    """Заголовок 'Этапы сбора данных'."""
    return '<div class="stage-title">Этапы сбора данных</div>\n'


def render_product_drive_block(ctx) -> str:
    """Блок 'Продукт + Google Drive клиента' — две ячейки.

    ctx: dict с полями a (заявка), product_label, product_code, product_select, drive_btn.
    """
    a = ctx["a"]
    product_label = ctx["product_label"]
    product_code = ctx["product_code"]
    product_select = ctx["product_select"]
    drive_btn = ctx["drive_btn"]
    from blocks.dashboard import page as _page
    price = _page.html.escape("{:,}".format(int(a["price_idr"]))) if a.get("price_idr") else "0"
    return (
        '<div class="row two-col stage-grid">\n'
        '  <div class="kv-cell stage-block">\n'
        '    <div class="stage-no">1</div>\n'
        '    <div class="kv-label">📦 Продукт</div>\n'
        f'    <div class="kv-main">{_page.html.escape(product_label)}</div>\n'
        f'    <div class="kv-sub">код: {_page.html.escape(product_code)} · IDR {price}</div>\n'
        f'    {product_select}\n'
        '  </div>\n'
        '  <div class="kv-cell stage-block">\n'
        '    <div class="stage-no">2</div>\n'
        '    <div class="kv-label">📁 Google Drive клиента</div>\n'
        f'    {drive_btn}\n'
        '  </div>\n'
        '</div>\n'
    )


# Реестр: какие блоки входят в страницу заявки и в каком порядке.
# Каждая запись — (tag, callable(ctx)). Будущая правка: добавить новый блок
# = зарегистрировать здесь + описать рендерер выше.
BLOCKS_REGISTRY = [
    ("comment",   render_comment_block),
    ("header",    render_app_header),
    ("intro",     render_stages_intro),
    ("product_drive", render_product_drive_block),
]


def render_blocks(ctx, *tags) -> str:
    """Собрать HTML из именованных блоков по их тегам."""
    out = []
    for tag, fn in BLOCKS_REGISTRY:
        if tag in tags:
            try:
                out.append(fn(ctx))
            except Exception as exc:                       # noqa: BLE001
                out.append(f"<!-- block {tag} failed: {exc} -->")
    return "".join(out)