"""Блок «Общее»: каркас страниц, стиль, меню, готовые компоненты интерфейса.

Правка здесь меняет вид всей системы. Экраны (blocks/*/page.py) только собирают
страницу из готовых кирпичиков: card(), item(), modal(), icol(), header_stats().
"""
from __future__ import annotations

from flask import Response, request, session

ICON_DASH = "M3 12l9-9 9 9M5 10v10h14V10"
ICON_USERS = "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"
ICON_DOC = "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6"
ICON_GEAR = ("M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a7.2 7.2 0 0 0 .1-1 7.2 7.2 0 0 0-.1-1l2-1.6"
             "-2-3.4-2.4 1a7 7 0 0 0-1.7-1L14.9 4h-4l-.4 2.6a7 7 0 0 0-1.7 1l-2.4-1-2 3.4L6 13.6"
             "a7.2 7.2 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 1.7 1l.4 2.6h4l.4-2.6a7 7 0 0 0 1.7-1l2.4 1 2-3.4z")
ICON_HIST = "M12 8v4l3 3M3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0z"

# Стили и логотип вшиваются в страницу (см. _inline_css/_logo_data_uri):
# на удалённом канале каждый отдельный запрос — лишняя задержка.
_CSS_MEM: dict = {}

# Новое меню: Главная / История / Шаблоны / Настройки. Клиенты — внутри карточки заявки.
MENU = [
    ("dashboard", "Новая заявка", "/", ICON_DASH),
    ("history",   "История и поиск", "/history", ICON_HIST),
    ("events",    "Журнал",   "/events",  ICON_HIST),
    # «|» в подписи = перенос строки в меню (в остальных местах — « · »)
    ("templates", "Конструктор|Продукты / Документы", "/templates", ICON_DOC),
    ("guide",     "Инструкция|Пакеты и переменные", "/guide", ICON_DOC),
    ("settings",  "Настройки", "/settings", ICON_GEAR),
]

CSS = """
:root{--bg:#EEF1F6;--card:#fff;--ink:#111827;--muted:#6B7280;--line:#E4E7EE;
  --accent:#1F6BFF;--accent2:#00A6D6;--danger:#E11D48;--ok:#0E9F6E;--warn:#B45309;
  --r:16px;--shadow:0 2px 10px rgba(17,24,39,.05)}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:var(--bg);color:var(--ink);font-size:15px;line-height:1.45;
  font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',Roboto,sans-serif}
a{color:var(--accent);text-decoration:none}

/* ---------- шапка: гамбургер слева + плашка сверху ---------- */
.topbar{position:sticky;top:0;z-index:30;background:var(--card);
  border-bottom:1px solid var(--line)}
.topbar-row{display:flex;align-items:center;gap:8px;padding:5px 14px;max-width:1180px;margin:0 auto}
@media(max-width:720px){
  /* на телефоне все элементы шапки одной высоты — иначе ряд выглядит рваным */
  .topbar-row{gap:8px;padding:9px 10px}
  .brand-pill,.topbar-user{height:36px;display:inline-flex;align-items:center;border-radius:10px}
  .brand-pill{padding:0 9px;min-width:0}
  .brand-pill b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .topbar-user{margin-left:auto;padding:0 11px}
}
.burger{width:36px;height:36px;border-radius:10px;background:transparent;border:1px solid var(--line);
  display:grid;place-items:center;cursor:pointer;color:var(--ink)}
.burger span{display:block;width:18px;height:2px;background:currentColor;border-radius:2px;
  position:relative}
.burger span::before,.burger span::after{content:"";position:absolute;left:0;
  width:100%;height:2px;background:currentColor;border-radius:2px}
.burger span::before{top:-6px}.burger span::after{top:6px}
.brand{font-weight:800;font-size:16px;display:flex;align-items:center;gap:9px;margin-left:auto}
.brand .logo{width:32px;height:32px;border-radius:10px;display:grid;place-items:center;font-size:17px;
  background:#fff;overflow:hidden}
.brand .logo img{width:100%;height:100%;object-fit:cover;border-radius:10px;display:block}
.brand-pill{padding:7px 12px 7px 8px;border-radius:14px;
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  display:flex;align-items:center;gap:9px;color:#fff;text-decoration:none;
  box-shadow:0 2px 8px rgba(31,107,255,.25)}
.brand-pill:active{filter:brightness(.92)}
.topbar-user{margin-left:8px;padding:6px 10px;border-radius:10px;background:#F3F5F9;
  font-size:12.5px;color:var(--ink);font-weight:600;white-space:nowrap}
@media(max-width:520px){.brand-pill b{display:none}.brand-pill{padding:7px}}
@media(max-width:380px){.topbar-user{display:none}}

/* зелёная шапка карточки клиента */
.client-head{background:linear-gradient(135deg,#0E9F6E,#15B07A);color:#fff;
  padding:18px 16px 22px;border-radius:18px;margin-bottom:14px;
  box-shadow:0 6px 18px rgba(14,159,110,.22)}
.client-head .clh-row{display:flex;align-items:center;gap:12px}
.client-head .clh-back{width:38px;height:38px;border-radius:12px;background:rgba(255,255,255,.18);
  color:#fff;display:grid;place-items:center;font-size:20px;border:none;cursor:pointer}
.client-head h1{margin:0;font-size:22px;font-weight:800}
.client-head .clh-sub{font-size:13px;opacity:.85;margin-top:4px}
.client-head .clh-chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.client-head .clh-chip{background:rgba(255,255,255,.18);padding:6px 11px;border-radius:18px;
  font-size:13px;font-weight:600}
.client-head .clh-chip b{font-weight:800;margin-right:5px}

/* верхняя плашка со статистикой заявок */
.stats-bar{display:flex;background:linear-gradient(135deg,var(--accent),var(--accent2));
  color:#fff;padding:10px 16px 12px;gap:14px;align-items:stretch}
.stats-bar .cell{flex:1;display:flex;flex-direction:column;gap:2px}
.stats-bar .lbl{font-size:11.5px;opacity:.85;text-transform:uppercase;letter-spacing:.4px}
.stats-bar .val{font-size:21px;font-weight:800;line-height:1.05}
.stats-bar .sub{font-size:12px;opacity:.85;margin-top:2px}
.stats-bar .sep{width:1px;background:rgba(255,255,255,.25);margin:0 2px}

/* боковое меню (drawer) */
.drawer{position:fixed;inset:0;background:rgba(17,24,39,.5);display:none;z-index:50}
.drawer.open{display:flex}
.drawer .panel{width:min(300px,82vw);background:#fff;height:100%;padding:18px 14px 24px;
  display:flex;flex-direction:column;gap:6px;box-shadow:8px 0 30px rgba(17,24,39,.18)}
.drawer .head{display:flex;align-items:center;gap:9px;padding:0 4px 14px;
  border-bottom:1px solid var(--line)}
.drawer .head b{font-weight:800;font-size:16px}
.drawer .head .logo{width:32px;height:32px;border-radius:10px;display:grid;place-items:center;
  font-size:17px;background:#fff;overflow:hidden}
.drawer .head .logo img{width:100%;height:100%;object-fit:cover;border-radius:10px;display:block}
.drawer nav{display:flex;flex-direction:column;gap:4px;padding-top:10px}
.drawer nav a{display:flex;align-items:center;gap:11px;padding:11px 12px;border-radius:12px;
  color:var(--ink);font-weight:600;font-size:15px}
.drawer nav a.active{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff}
.drawer nav a svg{width:19px;height:19px}
.drawer .close{margin-left:auto;background:none;border:none;font-size:22px;color:#9AA3B2;cursor:pointer}
.drawer .spacer{flex:1}
.drawer .user{color:var(--muted);font-size:13px;padding:10px 12px;border-top:1px solid var(--line)}

/* контент */
.wrap{max-width:1560px;margin:0 auto;padding:14px 20px 40px}
h1{font-size:22px;margin:2px 0 4px;font-weight:800;letter-spacing:-.2px}
h2{font-size:16px;margin:0 0 8px}
.page-sub{color:var(--muted);font-size:13px;margin-bottom:14px}

/* ---------- карточка-блок ---------- */
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);
  margin-bottom:12px;overflow:hidden}
.card>summary{list-style:none;display:flex;align-items:center;gap:12px;padding:14px 14px;cursor:pointer;
  font-weight:700;font-size:15.5px}
.card>summary::-webkit-details-marker{display:none}
.card>summary .chev{margin-left:auto;color:#9AA3B2;font-size:19px;line-height:1;transition:transform .18s}
.card[open]>summary .chev{transform:rotate(90deg)}
.card .body{padding:0 14px 14px}
.card .head-only{display:flex;align-items:center;gap:12px;padding:14px;font-weight:700;font-size:15.5px}
.card .head-only .chev{margin-left:auto;color:#9AA3B2}

/* строка с иконкой */
.item{display:flex;align-items:center;gap:12px;padding:11px 4px;color:inherit;
  border-top:1px solid var(--line)}
.item:first-child,.item.no-line{border-top:none}
.item .ico{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;font-size:19px;
  flex:none;background:#F3F5F9}
.item .txt{min-width:0;flex:1}
.item .t{font-weight:600;font-size:15px}
.item .s{color:var(--muted);font-size:12.5px;margin-top:1px}
.item .go{margin-left:auto;color:#9AA3B2;font-size:18px;flex:none}
a.item:active{background:#F7F9FD}
.ico.blue{background:#E7F0FF}.ico.green{background:#E6F7EE}.ico.red{background:#FFE9EC}
.ico.amber{background:#FFF3E0}.ico.violet{background:#F0EBFF}.ico.cyan{background:#E2F6FB}
.ico.grey{background:#F3F5F9}

/* кнопки */
/* кнопки: объёмные — с тенью снизу, подсветкой сверху и чётким нажатием */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:38px;padding:8px 14px;
  font-size:15px;font-weight:700;color:#fff;border:none;border-radius:12px;cursor:pointer;
  font-family:inherit;background:linear-gradient(135deg,var(--accent),var(--accent2));
  box-shadow:0 1px 0 rgba(255,255,255,.35) inset, 0 2px 3px rgba(16,24,32,.16),
             0 8px 18px rgba(31,107,255,.22);
  transition:box-shadow .12s ease, transform .08s ease, filter .12s ease}
.btn:hover{filter:brightness(1.05);
  box-shadow:0 1px 0 rgba(255,255,255,.4) inset, 0 3px 6px rgba(16,24,32,.18),
             0 10px 22px rgba(31,107,255,.26)}
.btn:active,.btn.is-press{transform:translateY(2px);
  box-shadow:inset 0 3px 8px rgba(0,0,0,.28), 0 1px 2px rgba(16,24,32,.12)}
.btn:disabled,.btn[disabled]{opacity:.72;transform:none;
  box-shadow:0 1px 2px rgba(16,24,32,.12)}
.btn.block{width:100%}
.btn.ghost{background:#fff;color:var(--ink);border:1px solid var(--line);
  box-shadow:0 1px 0 #fff inset, 0 2px 4px rgba(16,24,32,.10), 0 6px 14px rgba(16,24,32,.06)}
.btn.ghost:hover{box-shadow:0 1px 0 #fff inset, 0 3px 7px rgba(16,24,32,.14),
                 0 8px 18px rgba(16,24,32,.08)}
.btn.ghost:active{background:#F1F5FF;border-color:var(--accent);transform:translateY(2px);
  box-shadow:inset 0 2px 6px rgba(16,24,32,.12)}
.btn.danger{background:linear-gradient(135deg,var(--danger),#F43F5E);
  box-shadow:0 1px 0 rgba(255,255,255,.3) inset, 0 2px 3px rgba(16,24,32,.16),
             0 8px 18px rgba(225,29,72,.22)}
.btn.sm{min-height:34px;padding:6px 11px;font-size:13px;border-radius:10px;
  box-shadow:0 1px 0 rgba(255,255,255,.3) inset, 0 1px 2px rgba(16,24,32,.14),
             0 4px 10px rgba(31,107,255,.16)}
.btn.sm:active{transform:translateY(1px);box-shadow:inset 0 2px 6px rgba(0,0,0,.24)}
.btn.ok{background:linear-gradient(135deg,var(--ok),#15B07A);
  box-shadow:0 1px 0 rgba(255,255,255,.3) inset, 0 2px 3px rgba(16,24,32,.16),
             0 8px 18px rgba(14,159,110,.22)}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.row.tight{margin-bottom:12px}

/* метки */
.badge{display:inline-block;font-size:12px;font-weight:700;padding:3px 9px;border-radius:18px;
  background:#EEF2FF;color:#3B49C4}
.badge.ok{background:#E6F7EE;color:var(--ok)}
.badge.warn{background:#FFF3E0;color:var(--warn)}
.badge.bad{background:#FFE9EC;color:var(--danger)}
.badge.muted{background:#F3F5F9;color:#6B7280}

/* индикатор готовности документов в списке заявок */
.docs-state{display:inline-flex;align-items:center;gap:5px;font-size:12.5px;font-weight:600}
.docs-state .dot{width:9px;height:9px;border-radius:50%}
.docs-state.ok .dot{background:var(--ok)}.docs-state.warn .dot{background:var(--warn)}
.docs-state.bad .dot{background:var(--danger)}.docs-state.idle .dot{background:#C7CCD8}

/* поля */
label{display:block;font-size:12.5px;color:var(--muted);margin:10px 0 4px;font-weight:600}
input[type=text],input[type=password],input[type=file],textarea,select{
  width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:12px;background:#fff;
  color:var(--ink);font-family:inherit;font-size:15px}
input:focus,textarea:focus,select:focus{outline:none;border-color:var(--accent);
  box-shadow:0 0 0 3px rgba(31,107,255,.14)}
.kv{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
@media(max-width:720px){.kv,.grid3{grid-template-columns:1fr}}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;color:var(--muted);font-weight:700;font-size:11.5px;text-transform:uppercase;
  letter-spacing:.4px;padding:8px 6px;border-bottom:1px solid var(--line)}
td{padding:10px 6px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:none}
.muted{color:var(--muted);font-size:13px}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:12.5px}
.hint{background:#E7F0FF;border-radius:12px;padding:10px 12px;font-size:13px;color:#1D3E86}
.flash{border-radius:12px;padding:10px 12px;margin-bottom:10px;font-size:14px;font-weight:600}
.flash.ok{background:#E6F7EE;color:var(--ok)}
.flash.bad{background:#FFE9EC;color:var(--danger)}

/* всплывающее окно (bottom sheet) */
.modal{position:fixed;inset:0;background:rgba(17,24,39,.46);display:none;z-index:60;align-items:flex-end}
.modal.open{display:flex}
.modal .sheet{background:#fff;width:100%;border-radius:20px 20px 0 0;padding:16px 14px 24px;
  max-height:88vh;overflow:auto}
.modal .sheet h3{margin:0 0 6px;font-size:17px;font-weight:800}
.modal .grab{width:40px;height:5px;border-radius:4px;background:#DDE2EA;margin:0 auto 12px}
.modal .close-x{position:relative;float:right;border:none;background:none;font-size:22px;color:#9AA3B2;
  cursor:pointer;line-height:1}
@media(min-width:721px){.modal{align-items:center;justify-content:center}
  .modal .sheet{max-width:540px;border-radius:18px}}

/* нижняя навигация (компактная, дублирует drawer) */
.tabbar{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid var(--line);
  display:none;z-index:40;padding:6px 4px calc(6px + env(safe-area-inset-bottom))}
.tabbar a{flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;padding:6px 0;
  border-radius:11px;color:#8A93A5;font-size:10.5px;font-weight:600}
.tabbar a.active{color:var(--accent);background:#F1F5FF}
.tabbar svg{width:20px;height:20px}
@media(max-width:720px){
  .wrap{padding:12px 12px 24px}
  h1{font-size:19px}.page-sub{font-size:12.5px}
  .card>summary{padding:12px}.card .body{padding:0 12px 12px}
  .stats-bar{padding:8px 12px 10px}
  .stats-bar .val{font-size:18px}
}

/* === Универсальный Zoom+Pan для HTML/документ-превью === */
.zp-host{position:relative;overflow-y:scroll;overflow-x:auto;background:#E7EBEE;border:1px solid var(--line);
  border-radius:10px;height:auto;min-height:240px;max-height:78vh;
  scrollbar-width:thin;scrollbar-color:#A9B4BC #E7EBEE}
.zp-host::-webkit-scrollbar{width:12px;height:12px}
.zp-host::-webkit-scrollbar-track{background:#EDF1F4}
.zp-host::-webkit-scrollbar-thumb{background:#B7C1C8;border:3px solid #EDF1F4;border-radius:8px}
.zp-host::-webkit-scrollbar-thumb:hover{background:#98A5AE}
.zp-canvas{position:relative;margin:0 auto;transform-origin:top left}
/* лист документа: видимая граница A4 (белый лист на белом фоне не читался) */
.zp-canvas>.html-stage,.zp-canvas>.doc-html-stage,.zp-canvas>.pdf-preview{
  background:#fff;box-shadow:0 0 0 1px #E1E7E3,0 3px 14px rgba(16,32,24,.10)}
.zp-host[data-pannable="1"]{cursor:grab}
.zp-host.zp-dragging{cursor:grabbing;user-select:none}
.zp-host.zp-dragging *{user-select:none !important}
.zp-shell{display:flex;flex-direction:column;gap:6px}
.zp-tools{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;
  padding:0 2px}
.zp-bar{display:flex;gap:6px;align-items:center;background:#fff;border:1px solid var(--line);
  border-radius:10px;padding:4px 8px;font-size:12px;flex:0 0 auto}
.zp-bar button{border:1px solid var(--line);background:#fff;border-radius:8px;cursor:pointer;
  font-size:13px;line-height:1;padding:5px 10px;font-family:inherit;color:#1F2A24}
.zp-bar button:hover{background:#F2F7F4}
.zp-bar .zp-val{min-width:44px;text-align:center;font-weight:700;color:#1F2A24}
.zp-hint{font-size:11.5px;color:#6B7C70}

/* === Всплывающее окно инструкции переменной === */
.varmodal{position:fixed;left:50%;top:6vh;transform:translateX(-50%);width:min(680px,94vw);
  max-height:86vh;overflow:auto;background:#fff;border:1px solid #D8E2DC;border-radius:14px;
  box-shadow:0 18px 50px rgba(16,32,24,.28);z-index:80;display:none;padding:16px 18px 18px}
.varmodal.open{display:block}
/* подложка окна переменной: клик по ней (по любому месту вне окна) закрывает окно.
   Селектор без привязки к .varmodal — подложка живёт прямо в body, иначе position:fixed не применялся */
.vm-back{position:fixed;inset:0;background:rgba(17,24,39,.42);z-index:79;display:none}
.vm-back.open{display:block}
.varmodal h3{margin:0 0 4px;font-size:16px;font-weight:800;color:#14261C}
.varmodal .vm-rule{font-size:13.5px;line-height:1.5;color:#22352A;white-space:pre-wrap;
  max-height:54vh;overflow:auto;background:#F6F9F7;border:1px solid #DCE6E0;border-radius:10px;
  padding:12px 14px;margin-top:6px}
.varmodal .vm-rule .vm-line{margin:0 0 3px;white-space:pre-wrap}
.varmodal .vm-rule .vm-head{font-weight:800;color:#14261C;margin-top:12px;margin-bottom:4px}
.varmodal .vm-rule .vm-head:first-child{margin-top:0}
.varmodal .vm-rule .vm-gap{height:7px}
.varmodal .vm-sub{font-size:12px;color:#6B7C70;margin-bottom:10px}
.varmodal textarea{width:100%;min-height:150px;box-sizing:border-box;font-family:inherit;
  font-size:13.5px;line-height:1.45;padding:10px 12px;border:1px solid #D8E2DC;border-radius:10px;
  background:#FBFDFC;color:#16241C;resize:vertical}
.varmodal textarea:focus{outline:none;border-color:#16A34A;box-shadow:0 0 0 3px #DCFCE7}
.varmodal .vm-row{display:flex;gap:8px;align-items:center;margin-top:12px;flex-wrap:wrap}
.varmodal .vm-hint{flex:1 1 180px;font-size:11.5px;color:#6B7C70}
.varmodal .vm-btn{border:1px solid #D8E2DC;background:#fff;border-radius:10px;padding:9px 16px;
  font-size:13.5px;font-family:inherit;cursor:pointer;color:#14261C}
.varmodal .vm-btn.ok{background:#16A34A;border-color:#16A34A;color:#fff;font-weight:700}
.varmodal .vm-btn.ok:hover{background:#15803D}
.varmodal .vm-x{position:absolute;right:12px;top:10px;border:0;background:none;font-size:20px;
  color:#9AA3B2;cursor:pointer}
.varmodal .vm-lbl{display:block;font-size:11.5px;font-weight:700;color:#5A6B60;
  text-transform:uppercase;letter-spacing:.03em;margin:10px 0 5px}
.varmodal .vm-chat{max-height:220px;overflow:auto;background:#F7FAF8;border:1px solid #E1EAE4;
  border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:8px}
.varmodal .vm-chat .m{max-width:88%;padding:8px 11px;border-radius:12px;font-size:13px;
  line-height:1.42;white-space:pre-wrap;word-wrap:break-word}
.varmodal .vm-chat .m.user{align-self:flex-end;background:#DCFCE7;color:#14532D;border:1px solid #BBF7D0}
.varmodal .vm-chat .m.ai{align-self:flex-start;background:#fff;color:#1B2B22;border:1px solid #E1EAE4}
.varmodal .vm-chat .m.err{align-self:flex-start;background:#FEF2F2;color:#991B1B;border:1px solid #FECACA}
.varmodal .vm-inrow{display:flex;gap:8px;margin-top:8px;align-items:flex-end}
.varmodal .vm-inrow textarea{min-height:64px;flex:1 1 auto;margin:0}
.varmodal .vm-btn.ai{background:#1D4ED8;border-color:#1D4ED8;color:#fff;font-weight:700;white-space:nowrap}
.varmodal .vm-btn.ai:hover{background:#1E40AF}
.varmodal .vm-btn.ai:disabled{background:#93A6E0;border-color:#93A6E6;cursor:default}
.varmodal .vm-think{font-size:12px;color:#1D4ED8;margin-top:6px;display:none}
.varmodal .vm-think.on{display:block}

/* === Иконка «инструкция переменной» === */
.var-info{flex:0 0 auto;width:22px;height:22px;border-radius:50%;cursor:help;
  border:1px solid #BFD8FF;background:#EFF5FF;color:#1D4ED8;font-size:12.5px;font-weight:800;
  font-style:italic;line-height:1;display:inline-flex;align-items:center;justify-content:center;
  user-select:none;margin:0 2px}
.var-info:hover{background:#DBEAFE;border-color:#93C5FD}

/* === Подсветка переменной в документе (клик по номеру/названию/полю) === */
[data-var].var-flash, .var-flash{animation:varflash 1.1s ease-in-out 2;
  outline:3px solid #F59E0B !important;outline-offset:2px;border-radius:4px;
  background:#FEF3C7 !important;color:#78350F !important;position:relative;z-index:3}
@keyframes varflash{
  0%,100%{background:#FEF3C7;box-shadow:0 0 0 0 rgba(245,158,11,0)}
  50%{background:#FDE68A;box-shadow:0 0 0 6px rgba(245,158,11,.35)}
}
.var-row.var-active, .var-field.var-active{background:#FFF7E6 !important;
  box-shadow:inset 3px 0 0 #F59E0B}
.var-row, .var-field{cursor:pointer;transition:background .15s}
"""

JS = """
function openModal(id){var m=document.getElementById(id);if(m){m.classList.add('open');
  document.body.style.overflow='hidden';}}
function closeModal(id){var m=document.getElementById(id);if(m){m.classList.remove('open');
  document.body.style.overflow='';}}
function openDrawer(){var d=document.getElementById('drawer');if(d){d.classList.add('open')}}
function closeDrawer(){var d=document.getElementById('drawer');if(d){d.classList.remove('open')}}
document.addEventListener('click',function(e){
  var t=e.target;
  if(t.classList && t.classList.contains('modal')){closeModal(t.id);return;}
  if(t.classList && t.classList.contains('drawer')){closeDrawer();return;}
  var opener=t.closest && t.closest('[data-modal]');
  if(opener){e.preventDefault();openModal(opener.getAttribute('data-modal'));}
  var burger=t.closest && t.closest('[data-burger]');
  if(burger){e.preventDefault();openDrawer();}
});
document.addEventListener('keydown',function(e){if(e.key==='Escape'){
  document.querySelectorAll('.modal.open').forEach(function(m){closeModal(m.id);});
  closeDrawer();}});

/* === Универсальный Zoom + Pan для превью (любой контейнер с data-zoom-pan) === */
(function(){
  var A4W=794.5, A4H=1122.6;
  var MIN=.45, MAX=1.0;   /* 45% — ниже лист превращается в марку, а окно просмотра в полоску */
  /* Потолок масштаба — 100%: при увеличении свыше 100% ширина прокрутки окна
     раздувалась до миллионов пикселей и лист «улетал» вправо (документы №1, №3,
     №8, 04.10.2026). Выше 100% документ всё равно не читается лучше — «вписать»
     и уменьшение работают как раньше. */
  function init(host){
    if(host.dataset.zpReady) return; host.dataset.zpReady='1';
    host.classList.add('zp-host');
    var content=host.querySelector('.zp-content')||host.firstElementChild;
    if(!content) return;
    /* До первой подгонки масштаба лист не показываем: иначе документ на миг
       отрисовывается в натуральную величину и окно «прыгает». */
    content.style.visibility='hidden';
    var canvas=document.createElement('div'); canvas.className='zp-canvas';
    host.insertBefore(canvas,content); canvas.appendChild(content);
    var userScale=null, ox=0, oy=0, bx=0, by=0, s=.62;
    // Панель управления масштабом
    var bar=document.createElement('div'); bar.className='zp-bar';
    // ВАЖНО: строка статическая (без пользовательских данных) — XSS невозможен
    bar.innerHTML='<button type="button" data-zp="out" title="Уменьшить">\u2212</button>'+
      '<span class="zp-val">100%</span>'+
      '<button type="button" data-zp="in" title="Увеличить">+</button>'+
      '<button type="button" data-zp="fit" title="Центрировать лист в окне — показать целиком">'
      '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"'
      ' stroke-linecap="round"><rect x="1.6" y="1.6" width="12.8" height="12.8" rx="2.2"/>'
      '<circle cx="8" cy="8" r="1.7" fill="currentColor" stroke="none"/></svg></button>';
    var hint=null;   /* строка-подсказка убрана: место над окном больше не занимается */
    // Тулбар ВЫШЕ окна просмотра — не перекрывает документ и не прокручивается с ним
    var shell=document.createElement('div'); shell.className='zp-shell';
    var tools=document.createElement('div'); tools.className='zp-tools';
    /* Панель масштаба (−, %, +, вписать) переезжает наверх — в полосу вкладок окна,
       слева от кнопки «Просмотр PDF». Если полосы нет (старые страницы) — остаётся над окном. */
    var tabsBox=document.getElementById('doc-tabs');
    var pdfBtn=document.getElementById('tpl-pdf-open');
    if(tabsBox){ tabsBox.insertBefore(bar, pdfBtn || null); }
    else { tools.appendChild(bar); }
    if(host.parentNode) host.parentNode.insertBefore(shell, host);
    shell.appendChild(host);
    if(tools.childNodes.length) shell.insertBefore(tools, host);
    var valEl=bar.querySelector('.zp-val');
    /* ── Разбивка содержимого по листам A4 ────────────────────────────────────
       Шаблон задаёт лист как .sheet с min-height = высота A4. Когда содержимого
       больше, лист вырастал и переставал быть A4 — белое поле вытягивалось по
       вертикали. Переносим не влезающие внизу блоки на следующий лист. */
    function a4Box(sh){
      var cs=window.getComputedStyle?window.getComputedStyle(sh):null;
      var pageH=cs?(parseFloat(cs.minHeight)||0):0;
      if(!pageH||isNaN(pageH)) return null;
      var padB=cs?(parseFloat(cs.paddingBottom)||0):0;
      return {pageH:pageH, bottom:pageH-padB};
    }
    /* offsetTop/offsetHeight не зависят от transform:scale — считаем в натуральных
       координатах листа, поэтому масштаб окна разбивке не мешает. */
    function paginate(root){
      var list=[].slice.call(root.querySelectorAll('.sheet'));
      if(!list.length) return 0;
      var created=0;
      for(var i=0;i<list.length;i++){
        var sh=list[i], m=a4Box(sh);
        if(!m) continue;
        var pass=0;
        while(pass++<80){
          var last=sh.lastElementChild;
          if(!last) break;
          if(last.offsetTop+last.offsetHeight<=m.bottom+2) break;
          if(sh.children.length<=1) break;   /* один блок выше листа — рвать нечем */
          var next=sh.nextElementSibling;
          if(!next||!next.classList||!next.classList.contains('sheet')){
            next=document.createElement(sh.tagName||'div');
            next.className=sh.className;
            sh.parentNode.insertBefore(next,sh.nextSibling);
            list.splice(i+1,0,next); created++;
          }
          next.insertBefore(last,next.firstChild);
        }
      }
      return created;
    }
    var paging=false;
    function apply(){
      if(!paging){                         /* разбивка по листам — до подгонки масштаба */
        paging=true;
        try{ paginate(content); }catch(e){}
        paging=false;
      }
      var cw=host.clientWidth||600;
      // полоса прокрутки съедает часть окна — иначе правый край листа подрезается
      var sbw=Math.max(0,(host.offsetWidth||cw)-(host.clientWidth||cw));
      // поля окна (padding) входят в clientWidth — без вычета лист уезжает вправо
      var hcs=window.getComputedStyle?window.getComputedStyle(host):null;
      var padW=hcs?((parseFloat(hcs.paddingLeft)||0)+(parseFloat(hcs.paddingRight)||0)):0;
      var natW=content.offsetWidth||A4W, natH=content.offsetHeight||A4H;
      /* Сменился документ (другой шаблон, другая вкладка «Оригинал/Перевод») —
         визор забывает старую прокрутку и масштаб. Без этого новый лист
         показывался со сдвигом вправо: слева пустая полоса, документ за краем
         окна (документ №8 ходатайства D12 в конструкторе). */
      try{
        /* Подпись документа считаем ТОЛЬКО по естественным размерам листа.
           Раньше в неё входили число листов и длина текста — они меняются от
           самой разбивки и от масштаба, поэтому подпись «ложно» обновлялась и
           зум сбрасывался (документ №3, 04.10.2026: 66→79→95→66). */
        var sig=[natW,natH].join('x');
        if(host.dataset.zpSig!==sig){
          host.dataset.zpSig=sig;
          window.__zpUserScrolled=false;
          host.scrollLeft=0; host.scrollTop=0;
          delete host.dataset.zpShown;
          /* Масштаб, заданный пользователем, НЕ сбрасываем: подпись меняется и
             при пересборке листов, из-за чего зум «сам» возвращался к 66%
             (документ №3, 04.10.2026). В авторежиме масштаб пересчитается ниже. */
        }
      }catch(e){}
      var avail=Math.max(120, cw - padW - sbw - 8);   // 8 px — воздух по краям
      /* ОДИН расчёт масштаба — и он же окончательный. Раньше масштаб считался
         дважды: сначала по avail, потом «дожим» по cw-padW-8 без учёта полосы
         прокрутки. Второй расчёт делал канвас шире окна, появлялась
         горизонтальная прокрутка, и лист уезжал вправо (D12 в заявке, снова и
         снова). Теперь в авторежиме лист ГАРАНТИРОВАННО вписан по ширине:
         канвас никогда не шире окна, горизонтальной прокрутки нет, центрируют
         auto-поля. Ручной масштаб (колёсико, «+»/«−») — единственный случай,
         когда прокрутка разрешена. */
      if(userScale===null){
        s=Math.max(0.05, Math.min(avail/natW, 1));
      } else {
        s=Math.max(0.05, Math.min(userScale, MAX));
      }
      content.style.transform='scale('+s+')';
      content.style.transformOrigin='top left';
      // Канвас занимает МАСШТАБИРОВАННЫЙ размер → появляется нативная прокрутка
      canvas.style.width=Math.ceil(natW*s)+'px';
      canvas.style.height=Math.ceil(natH*s)+'px';
      canvas.style.marginLeft='auto';
      canvas.style.marginRight='auto';
      var cwv=Math.ceil(natW*s);
      if(userScale===null){
        /* Лист вписан: по горизонтали прокрутки быть не должно ни при каких
           обстоятельствах — иначе лист «убегает» за правый край. */
        host.style.overflowX='hidden';
        host.scrollLeft=0;
      } else {
        host.style.overflowX='auto';
        if(cwv>cw+1 && !window.__zpUserScrolled){ host.scrollLeft=Math.max(0, Math.round((cwv-cw)/2)); }
      }
      // Окно: высота листа, но не больше 78% экрана (без пустых полей)
      // При переключении вкладок высоту НЕ трогаем (window.__zpHoldWindow): иначе окно
      // меняет размер, страница перекомпоновывается и кажется, что «прыгнул весь сайт».
      var maxH=Math.max(240,Math.round((window.innerHeight||800)*0.78));
      var targetH=Math.min(Math.ceil(natH*s),maxH);
      if(!window.__zpHoldWindow && !window.__zpFreezeH && Math.abs((host.clientHeight||0)-targetH)>1) host.style.height=targetH+'px';
      var ch=host.clientHeight||targetH;
      host.dataset.pannable=(natH*s>ch+1||natW*s>cw+1)?'1':'0';
      valEl.textContent=Math.round(s*100)+'%';
      /* Первый расчёт: показываем лист уже вписанным и ставим вид в начало —
         документ сразу по центру, окно больше не дёргается. */
      if(!host.dataset.zpShown){
        host.dataset.zpShown='1';
        window.__zpUserScrolled=false;   /* первый показ — лист центрируем */
        host.scrollLeft=0; host.scrollTop=0;
        content.style.visibility='';
      }
      clampScroll();
    }
    /* Ограничитель прокрутки: после любого пересчёта масштаба, зума, панорамы и
       изменения размеров окна прокрутка не может выйти за пределы листа. Без него
       визор «уезжал» вправо: лист оставался в старом scrollLeft, когда окно
       меняло ширину (документ №3, 04.10.2026). */
    /* Пределы прокрутки считаем ОТ НАТУРАЛЬНОГО размера листа, а не от
       host.scrollWidth: при ручном увеличении свыше 100% ширину прокрутки
       раздувало до миллионов пикселей (документ №3, 04.10.2026), и лист улетал
       вправо — центр брался от этой раздутой величины. */
    function scrollLimits(){
      var cwv=Math.ceil((content.offsetWidth||794.5)*s);
      var chv=Math.ceil((content.offsetHeight||1123)*s);
      return {maxL:Math.max(0,cwv-(host.clientWidth||0)),
              maxT:Math.max(0,chv-(host.clientHeight||0))};
    }
    function clampScroll(){
      if(!host) return;
      var lim=scrollLimits();
      /* Предохранитель: если окно «раздуто» сверх листа (глюк масштабирования) —
         прокрутку в пустоту не допускаем, лист просто встаёт к левому краю. */
      if((host.scrollWidth||0) > Math.ceil((content.offsetWidth||794.5)*s)+80) host.scrollLeft=0;
      if(host.scrollLeft>lim.maxL) host.scrollLeft=lim.maxL;
      if(host.scrollLeft<0) host.scrollLeft=0;
      if(host.scrollTop>lim.maxT) host.scrollTop=lim.maxT;
      if(host.scrollTop<0) host.scrollTop=0;
    }
    /* Зум: масштаб меняется от текущего и центр листа остаётся на месте —
       иначе при «+» документ «убегает» влево (заявка #76, 04.10.2026). */
    function zoomBy(f){
      window.__zpUserScrolled=true;     /* пользователь сам задал масштаб — не центруем насильно */
      var old=(userScale||s);
      var nv=Math.max(MIN,Math.min(old*f,MAX));
      if(!host) return;
      var cx=host.scrollLeft+host.clientWidth/2, cy=host.scrollTop+host.clientHeight/2;
      userScale=nv; apply();
      /* Лист держим по центру окна, но центр считаем от натуральной ширины листа:
         host.scrollWidth при увеличении раздувается, и лист «уползал» вправо. */
      var lim=scrollLimits();
      host.scrollLeft = lim.maxL>1 ? Math.round(lim.maxL/2) : 0;
      var k=nv/old;
      host.scrollTop=Math.max(0,Math.min(lim.maxT,Math.round(cy*k-host.clientHeight/2)));
      clampScroll();
    }
    // Центрировать вид на элементе (для подсветки переменной)
    function focusEl(el){
      if(!el||!el.getBoundingClientRect) return;
      var hr=host.getBoundingClientRect(), r=el.getBoundingClientRect();
      /* По горизонтали не прокручиваем, если лист вписан (автомасштаб): иначе
         подсветка переменной уводила лист вбок за край окна. */
      var lockX=(host.style.overflowX==='hidden');
      var left=lockX?0:Math.max(0,host.scrollLeft+(r.left-hr.left)-host.clientWidth/2+r.width/2);
      try{
        host.scrollTo({
          left:left,
          top :Math.max(0,host.scrollTop +(r.top -hr.top )-host.clientHeight/2+r.height/2),
          behavior:'smooth'});
      }catch(e){
        host.scrollLeft=left;
        host.scrollTop =Math.max(0,host.scrollTop +(r.top -hr.top )-host.clientHeight/2+r.height/2);
      }
    }
    bar.addEventListener('click',function(e){
      var b=e.target.closest('[data-zp]'); if(!b) return; e.preventDefault();
      var a=b.getAttribute('data-zp');
      if(a==='in') zoomBy(1.2);
      else if(a==='out') zoomBy(1/1.2);
      /* Вписать: считаем один раз и обнуляем прокрутку. Второй пересчёт пробовал —
         он давал 76% вместо 80% на длинных документах (после появлялась полоса). */
      else if(a==='fit'){ userScale=null; window.__zpUserScrolled=false; apply(); host.scrollTop=0; host.scrollLeft=0;
        /* дожим: окно могло измениться, пока считали — центрируем лист по обеим осям */
        setTimeout(function(){ if(!userScale){ apply(); host.scrollTop=0; host.scrollLeft=0; } }, 60); }
    });
    /* Окно визора на странице заявки уже, чем в конструкторе шаблона: пока страница
       раскладывается, ширина меняется и лист оказывался обрезанным (заявка #76).
       Если масштаб не задан вручную — пересчитываем вписывание при смене ширины. */
    try{
      if(window.ResizeObserver){
        var _roLastW=Math.round(host.clientWidth||0);
        new ResizeObserver(function(){
          var w=Math.round(host.clientWidth||0);
          if(w && Math.abs(w-_roLastW)>2){
            var prevW=_roLastW; _roLastW=w;
            /* В авторежиме пересчитываем вписывание; в ручном — сохраняем масштаб,
               но прокрутку подрезаем по новым размерам, иначе лист уезжает вбок. */
            if(!userScale){ apply(); host.scrollLeft=0; }
            else if(w<prevW){ clampScroll(); }
            else { clampScroll(); }
          }
        }).observe(host);
      }
    }catch(e){}
    // Ctrl+колесо — зум (обычное колесо = нативный скролл)
    host.addEventListener('wheel',function(e){
      if(e.ctrlKey||e.metaKey){ e.preventDefault(); zoomBy(e.deltaY<0?1.12:1/1.12); }
    },{passive:false});
    // Drag-to-pan через нативную прокрутку
    var panning=false,sx=0,sy=0,sl=0,st=0;
    function down(e){
      if(e.button!==undefined&&e.button!==0) return;
      /* Клик по кнопке (галочка/крестик, ссылки) — не начало перетаскивания листа */
      var t=e.target;
      if(t && t.closest && t.closest('button,a,.doc-verdict-float')) return;
      if(host.dataset.pannable!=='1') return;
      panning=true; sx=e.clientX; sy=e.clientY; sl=host.scrollLeft; st=host.scrollTop;
      host.classList.add('zp-dragging'); e.preventDefault();
    }
    function move(e){
      if(!panning) return;
      window.__zpUserScrolled=true;      /* лист двигают мышью — автоцентрирование отключаем */
      host.scrollLeft=sl-(e.clientX-sx); host.scrollTop=st-(e.clientY-sy);
    }
    function up(){ if(!panning) return; panning=false; host.classList.remove('zp-dragging'); }
    host.addEventListener('mousedown',down);
    document.addEventListener('mousemove',move);
    document.addEventListener('mouseup',up);
    // Масштаб ставим сразу и повторяем, когда догрузились шрифты и картинки листа:
    // раньше подгонка «догоняла» страницу уже после открытия
    apply();
    if(document.fonts && document.fonts.ready) document.fonts.ready.then(function(){ if(userScale===null) apply(); });
    window.addEventListener('load', function(){ if(userScale===null) apply(); });
    if(typeof ResizeObserver!=='undefined'){
      var ro=new ResizeObserver(function(){ if(userScale===null) apply(); });
      ro.observe(content);
    }
    host.addEventListener('touchstart',function(e){
      if(host.dataset.pannable==='1'&&e.touches.length===1){
        panning=true; sx=e.touches[0].clientX; sy=e.touches[0].clientY;
        sl=host.scrollLeft; st=host.scrollTop; host.classList.add('zp-dragging'); }
    },{passive:true});
    host.addEventListener('touchmove',function(e){
      if(panning&&e.touches.length===1){
        host.scrollLeft=sl-(e.touches[0].clientX-sx);
        host.scrollTop =st-(e.touches[0].clientY-sy); }
    },{passive:true});
    host.addEventListener('touchend',up);
    window.addEventListener('resize',apply);
    host.zpApply=apply;
    host.zpFocus=focusEl;
    try{ new ResizeObserver(function(){ apply(); }).observe(content); }catch(e){}
    apply();
    [80,300,900].forEach(function(t){ setTimeout(apply,t); });
  }
  function scan(root){
    (root||document).querySelectorAll('[data-zoom-pan]').forEach(init);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',function(){scan();});
  else scan();
  setTimeout(function(){scan();},400);
  setTimeout(function(){scan();},1500);
  // динамически добавленные превью
  try{ new MutationObserver(function(){ scan(); }).observe(document.body,{childList:true,subtree:true}); }catch(e){}
  window.zpScan=scan;
})();

/* === Окно инструкции переменной: только правило формирования (без чата и правки) === */
(function(){
  var back=null, box=null;
  function ensure(){
    if(box) return;
    back=document.createElement('div'); back.className='vm-back';
    box=document.createElement('div'); box.className='varmodal';
    // ВАЖНО: разметка статическая, текст правила вставляется через textContent
    box.innerHTML='<button type="button" class="vm-x" title="Закрыть">\u00d7</button>'
      +'<h3 class="vm-title"></h3><div class="vm-sub"></div>'
      +'<span class="vm-lbl">Как формируется эта переменная</span>'
      +'<div class="vm-rule"></div>';
    document.body.appendChild(back); document.body.appendChild(box);
    back.addEventListener('click', close);
    // клик по подложке вне окна закрывает его; Esc — тоже
    document.addEventListener('keydown', function(e){ if(e.key === 'Escape') close(); });
    // страховка: клик по любому месту вне окна (по нижележащему слою) закрывает окно
    document.addEventListener('click', function(e){
      if(!box || !box.classList.contains('open')) return;
      var t = e.target; if(!t || !t.closest) return;
      if(t.closest('.varmodal') || t.closest('.var-info')) return;
      close();
    }, true);
    box.querySelector('.vm-x').addEventListener('click', close);
  }
  function close(){ if(box) box.classList.remove('open'); if(back) back.classList.remove('open'); }
  document.addEventListener('click', function(e){
    var t=e.target; if(!t||!t.closest) return;
    var ic=t.closest('.var-info'); if(!ic) return;
    e.preventDefault(); e.stopPropagation();
    ensure();
    var name=ic.dataset.var||'';
    box.querySelector('.vm-title').textContent='Переменная: '+name;
    box.querySelector('.vm-sub').textContent='Документ: '+(ic.dataset.doc||'')+' — инструкция по заполнению';
    var host=box.querySelector('.vm-rule');
    host.textContent='';
    var text=(ic.dataset.rule||'').trim() || 'Инструкция для этой переменной пока не заполнена.';
    // каждая строка правила — отдельная строка; «Заголовок:» выделяем жирным
    text.split(String.fromCharCode(10)).forEach(function(line){
      var s=line.trimEnd();
      var d=document.createElement('div');
      d.className = s==='' ? 'vm-gap' : (/^[^:.]{2,70}:$/.test(s) ? 'vm-line vm-head' : 'vm-line');
      d.textContent=s;
      host.appendChild(d);
    });
    box.classList.add('open'); back.classList.add('open');
  }, true);
})();

/* === Подсветка переменной: клик по полю/номеру ↔ подсветка в документе === */
(function(){
  function esc(s){
    if(window.CSS&&CSS.escape) return CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g,'');
  }
  function clearAll(){ document.querySelectorAll('.var-flash,.var-active').forEach(function(x){
    x.classList.remove('var-flash'); x.classList.remove('var-active'); }); }
  function flashList(list,ms){
    if(!list.length) return;
    list.forEach(function(x){ x.classList.add('var-flash');
      setTimeout(function(){ x.classList.remove('var-flash'); }, ms||2600); });
  }
  document.addEventListener('click',function(e){
    var t=e.target; if(!t||!t.closest) return;
    var hit=t.closest('[data-var]'); if(!hit) return;
    var name=hit.getAttribute('data-var'); if(!name) return;
    var inDoc=!!t.closest('[data-zoom-pan],.doc-html-stage,.doc-html-stage-wrap');
    var sel='[data-zoom-pan] [data-var="'+esc(name)+'"], .doc-html-stage [data-var="'+esc(name)+'"], .zp-content [data-var="'+esc(name)+'"]';
    if(inDoc){
      // кликнули В документе → подсветить поле/строку слева
      var rows=document.querySelectorAll('.var-row[data-var="'+esc(name)+'"], .var-field[data-var="'+esc(name)+'"]');
      clearAll();
      rows.forEach(function(r){ r.classList.add('var-active');
        setTimeout(function(){ r.classList.remove('var-active'); },2600); });
      if(rows.length){
        var row=rows[0];
        /* Прокручиваем ТОЛЬКО панель переменных: каркас сайта и окно просмотра
           остаются на месте, а строка встаёт напротив выбранного места. */
        var sc=null, p=row.parentElement;
        while(p && p!==document.body){
          var cs=(window.getComputedStyle?getComputedStyle(p):null);
          if(cs && /(auto|scroll)/.test(cs.overflowY) && p.scrollHeight>p.clientHeight+2){ sc=p; break; }
          p=p.parentElement;
        }
        if(sc){
          var rr=row.getBoundingClientRect(), sr=sc.getBoundingClientRect();
          var top=sc.scrollTop + (rr.top - sr.top) - (sc.clientHeight/2) + (rr.height/2);
          try{ sc.scrollTo({top:Math.max(0,top),behavior:'smooth'}); }
          catch(err){ sc.scrollTop=Math.max(0,top); }
        } else {
          row.scrollIntoView({block:'nearest',behavior:'smooth'});
        }
      }
      flashList([hit]);
    } else {
      // кликнули слева → подсветить в документе + центрировать вид
      var targets=document.querySelectorAll(sel);
      if(!targets.length){ flashList([hit]); return; }
      clearAll();
      flashList(targets);
      var first=targets[0];
      var host=first.closest('[data-zoom-pan]');
      if(host&&host.zpFocus) host.zpFocus(first);
      var row=hit.closest('.var-row,.var-field');
      if(row){ row.classList.add('var-active');
        setTimeout(function(){ row.classList.remove('var-active'); },2600); }
    }
  },true);
})();

/* ── Подсказки при наведении у кнопок ─────────────────────────────────────────
   Навёл курсор — видно, что делает кнопка. Иконочные кнопки распознаём по коду
   символа (без escape-последовательностей), остальным подставляем их подпись. */
(function () {
  function clean(t) { return (t || '').replace(/️/g, '').replace(/‍/g, '').replace(/\s+/g, ' ').trim(); }
  function decorate(el) {
    if (!el || el.title) return;
    var txt = clean(el.textContent) || (el.getAttribute('aria-label') || '');
    if (!txt) return;
    var c = txt.codePointAt(0);
    var hint = null;
    if (c === 128065) hint = 'Показать документ';
    else if (c === 9999) hint = 'Редактировать документ заявки';
    else if (c === 128196) hint = 'Сформировать PDF и посмотреть';
    else if (c === 10003) hint = 'Проверен — документ согласован. Нажмите, чтобы снять проверку';
    else if (c === 10005) hint = 'Не нужен — исключить документ из комплекта';
    else if (c === 9881) hint = 'Настройки';
    else if (c === 9776) hint = 'Меню';
    else if (c === 128228) hint = 'Отправить документы на Google Диск';
    else if (c === 128269) hint = 'Найти';
    else if (c === 128221) hint = 'Сформирован PDF — открыть';
    if (hint) { el.title = hint; return; }
    if (txt.length >= 2) el.title = txt;
  }
  var SEL = 'button, a.btn, .doc-btn, .drive-btn, .tpl-btn, .btn-primary, input[type="submit"],' +
            '.drive-scan-btn, .tb-btn, .vm-btn, .ls-btn, .suggest-btn, .random-btn';
  function sweep(r) { (r || document).querySelectorAll(SEL).forEach(decorate); }
  sweep(document);
  document.addEventListener('mouseover', function (e) {
    var el = e.target && e.target.closest ? e.target.closest(SEL) : null;
    if (el) decorate(el);
  });
})();

// Показываем время загрузки в заголовке вкладки: по этой цифре видно, где
// остаётся задержка — на сервере или в канале до администратора.
// Упреждающая загрузка: как только курсор или палец коснулся ссылки на заявку,
// тянем её страницу заранее. К моменту нажатия она уже в кэше браузера, и
// открытие выглядит мгновенным.
(function () {
  var pulled = {};
  function warmLink(e) {
    var el = e.target;
    while (el && el.tagName !== 'A') el = el.parentNode;
    if (!el || !el.getAttribute) return;
    var href = el.getAttribute('href') || '';
    if (href.indexOf('/applications/') !== 0 && href.indexOf('/templates/') !== 0) return;
    if (pulled[href]) return;
    pulled[href] = 1;
    var link = document.createElement('link');
    link.rel = 'prefetch';
    link.href = href;
    document.head.appendChild(link);
  }
  document.addEventListener('mouseover', warmLink, { passive: true, capture: true });
  document.addEventListener('touchstart', warmLink, { passive: true, capture: true });
})();

window.addEventListener('load', function () {
  try {
    var t = performance.timing || {};
    var ms = Math.round((t.loadEventEnd || 0) - (t.navigationStart || 0));
    if (ms > 0 && document.title.indexOf(' мс') < 0) {
      document.title = document.title + ' · ' + ms + ' мс';
    }
  } catch (e) {}
});
"""


def icol(emoji: str, tone: str = "grey") -> str:
    return f'<div class="ico {tone}">{emoji}</div>'


def item(emoji: str, title: str, sub: str = "", href: str = "", tone: str = "blue",
         go: bool = True, extra: str = "") -> str:
    sub_html = f'<div class="s">{sub}</div>' if sub else ""
    go_html = '<div class="go">›</div>' if go else ""
    inner = (f'{icol(emoji, tone)}<div class="txt"><div class="t">{title}</div>{sub_html}</div>'
             f'{extra}{go_html}')
    if href:
        return f'<a class="item" href="{href}">{inner}</a>'
    return f'<div class="item">{inner}</div>'


def card(title: str, body: str, emoji: str = "", open: bool = False, tone: str = "grey",
         note: str = "", head_only: bool = False, head_extra: str = "") -> str:
    icon = icol(emoji, tone) if emoji else ""
    note_html = f'<span class="muted" style="font-weight:500">{note}</span>' if note else ""
    head = f'{icon}<span>{title}</span>{note_html}{head_extra}<span class="chev">›</span>'
    if head_only:
        return f'<div class="card"><div class="head-only">{head}</div></div>'
    return (f'<details class="card"{" open" if open else ""}>'
            f'<summary>{head}</summary><div class="body">{body}</div></details>')


def modal(modal_id: str, title: str, body: str) -> str:
    return (f'<div class="modal" id="{modal_id}"><div class="sheet"><div class="grab"></div>'
            f'<button class="close-x" onclick="closeModal(\'{modal_id}\')">✕</button>'
            f'<h3>{title}</h3>{body}</div></div>')


def modal_button(label: str, modal_id: str, cls: str = "btn ghost sm") -> str:
    return f'<button type="button" class="{cls}" data-modal="{modal_id}">{label}</button>'


def flash_messages():
    from flask import get_flashed_messages
    out = []
    for cat, msg in get_flashed_messages(with_categories=True):
        css = "bad" if cat in ("error", "bad") else "ok"
        out.append(f'<div class="flash {css}">{msg}</div>')
    return "".join(out)


def header_stats(apps_in: int, sum_in: int, apps_total: int, sum_total: int) -> str:
    """Верхняя плашка: количество заявок (слева) + общая сумма IDR (справа). Только на главной."""
    def fmt(n):
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f} млн".replace(".0 млн", " млн")
        if n >= 1000:
            return f"{n // 1000} тыс"
        return str(n)
    return f"""
<div class="stats-bar">
  <div class="cell">
    <div class="lbl">Количество заявок</div>
    <div class="val">{apps_in}</div>
    <div class="sub">всего {apps_total}</div>
  </div>
  <div class="sep"></div>
  <div class="cell" style="text-align:right">
    <div class="lbl">Общая сумма</div>
    <div class="val">IDR {fmt(sum_in)}</div>
    <div class="sub">всего IDR {fmt(sum_total)}</div>
  </div>
</div>
"""


def docs_state(summary: dict) -> tuple:
    """По сводке документов заявки: ('ok'|'warn'|'bad'|'idle', подпись)."""
    if summary.get("error"):
        return "bad", f'ошибка: {summary["error"]}'
    if summary.get("total", 0) == 0:
        return "idle", "документов пока нет"
    if summary.get("sent", 0) == summary["total"]:
        return "ok", f'готовы {summary["sent"]}/{summary["total"]}, отправлены'
    if summary.get("error", 0) > 0:
        return "bad", f'ошибок {summary["error"]}, готово {summary.get("verified", 0) or summary.get("filled", 0)}'
    if summary.get("verified", 0) == summary["total"]:
        return "ok", f'проверены {summary["verified"]}/{summary["total"]}'
    if summary.get("filled", 0) > 0:
        _left = max(int(summary["total"]) - int(summary["filled"]), 0)
        _tail = (", осталось %d" % _left) if _left else ", всё заполнено"
        return "warn", f'заполнено {summary["filled"]}/{summary["total"]}{_tail}'
    return "idle", f'в очереди {summary["total"]}'


def docs_state_html(summary: dict) -> str:
    state, label = docs_state(summary)
    return f'<span class="docs-state {state}"><span class="dot"></span>{label}</span>'


def _glyph(path: str) -> str:
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" '
            f'stroke-linecap="round" stroke-linejoin="round"><path d="{path}"/></svg>')


def _user_label() -> str:
    from core.auth import current_user
    u = current_user()
    if not u:
        return ""
    # Если есть Telegram-привязка — берём реальное имя и username из bot_managers.
    name = u.get("name") or ""
    role = u.get("role") or ""
    if not name:
        return ""
    # Если роль из bot_managers перебила users — показываем both как «admin»,
    # потому что на сайте он видит всё равно как админ.
    role_label = "admin" if role == "admin" else role or ""
    if role_label:
        return f"Личный кабинет · {name} ({role_label})"
    return f"Личный кабинет · {name}"


def _minify_css(css: str) -> str:
    """Сжимаем стили: убираем комментарии и лишние пробелы.

    Строки в кавычках не трогаем — в них пробелы значимые (шрифты, content).
    Стилей больше 100 КБ, и они уходят в каждый ответ, поэтому экономия заметна.
    """
    out = []
    i, n = 0, len(css)
    in_str = ""
    while i < n:
        ch = css[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(css[i + 1])
                i += 2
                continue
            if ch == in_str:
                in_str = ""
            i += 1
            continue
        if ch in "\"'":
            in_str = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and css[i + 1] == "*":
            j = css.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if ch in " \t\r\n":
            j = i
            while j < n and css[j] in " \t\r\n":
                j += 1
            prev = out[-1] if out else ""
            nxt = css[j] if j < n else ""
            if out and (prev in "{};,>+~" or nxt in "{};,>+~"):
                i = j
                continue
            out.append(" ")
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _minify_js(js: str) -> str:
    """Сжимаем скрипты: убираем комментарии, отступы и пустые строки.

    Строки, шаблоны и регулярки не трогаем — иначе легко сломать код.
    После сжатия проверяем синтаксис Node; не сошлось — отдаём как было.
    """
    import re as _re
    out = []
    i, n = 0, len(js)
    quote = ""
    while i < n:
        ch = js[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(js[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and js[i + 1] == "*":
            end = js.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        if ch == "/" and i + 1 < n and js[i + 1] == "/":
            end = js.find("\n", i)
            i = n if end < 0 else end
            continue
        out.append(ch)
        i += 1
    text = "".join(out)
    text = _re.sub(r"[ \t]+", " ", text)
    text = _re.sub(r"\n\s*\n+", "\n", text)
    text = "\n".join(line.strip() for line in text.split("\n") if line.strip())
    return text


def _js_syntax_ok(js: str) -> bool:
    """Проверяем сжатый скрипт через Node: ошибка — не применяем сжатие."""
    import subprocess as _sp
    import tempfile as _tf
    try:
        with _tf.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write(js)
            path = fh.name
        res = _sp.run(["node", "--check", path], capture_output=True, timeout=20)
        return res.returncode == 0
    except Exception:
        return False


_FILES_MEM: dict = {}


def front_bundle(kind: str):
    """Собираем общий код интерфейса в один файл: CSS или JS.

    Возвращает (текст, отпечаток). Отпечаток идёт в имя файла, поэтому браузер
    может держать файл в кэше год: при повторных заходах код интерфейса не
    скачивается заново — грузятся только данные заявки.
    """
    import hashlib as _hl
    from pathlib import Path as _P
    css_dir = _P("/opt/wolf_v2/blocks/static/css")
    chunks = []
    if kind == "css":
        for f in sorted(css_dir.glob("*.css")):
            if ".bak" in f.name:
                continue
            chunks.append(f.read_text(encoding="utf-8"))
        chunks.append(CSS)               # общие стили из этого модуля — последними
    else:
        chunks.append(JS)
    raw = "\n".join(chunks)
    if kind == "css":
        text = _minify_css(raw)
    else:
        text = raw
        try:
            packed = _minify_js(raw)
            if len(packed) < len(raw) and _js_syntax_ok(packed):
                text = packed
        except Exception:
            text = raw
    digest = _hl.sha1(text.encode("utf-8")).hexdigest()[:12]
    _FILES_MEM[digest] = text
    return text, digest


def front_asset_url(kind: str) -> str:
    """Ссылка на файл фронта с версией по содержимому."""
    try:
        _text, digest = front_bundle(kind)
        return "/front/wolf.%s.%s" % (digest, kind)
    except Exception:
        return ""


def render(title: str, active: str, body: str, crumbs: str = "", topbar: str = "",
              back: str = "") -> Response:
    drawer_links = []
    for key, label, href, icon in MENU:
        cls = "active" if key == active else ""
        _lbl_html = label.replace("|", "<br>")
        drawer_links.append(f'<a class="{cls}" href="{href}">{_glyph(icon)}{_lbl_html}</a>')
    # Полоса разделов: узкий вертикальный ряд иконок (по макету) + поиск и дата в шапке.
    rail_html = "".join(
        f'<a class="rail-i{" is-on" if key == active else ""}" href="{href}" '
        f'title="{label.replace("|", " · ")}" aria-label="{label.replace("|", " ")}">{_glyph(icon)}</a>'
        for key, label, href, icon in MENU
        if key not in ("logout",))
    import datetime as _dt
    _mon = ("января", "февраля", "марта", "апреля", "мая", "июня",
            "июля", "августа", "сентября", "октября", "ноября", "декабря")
    _now = _dt.datetime.now()
    date_label = f"{_now.day} {_mon[_now.month - 1]} {_now.year}, {_now:%H:%M}"
    from core.auth import current_user
    u = current_user()
    who_name = (u.get("name") if u else "") or session.get("user_name", "")
    who = f'<div class="user">{who_name} · <a href="/logout">выйти</a></div>' \
        if session.get("user_id") else ""
    # Крошки — в шапке, на всех страницах: путь по сайту всегда виден и закреплён
    # при прокрутке. Если страница не передала свои крошки — строим из меню.
    if not crumbs:
        if active == "dashboard":
            crumbs = ("" if title == "Главная"
                      else f'<a href="/">Главная</a> &rsaquo; <b>{title}</b>')
        else:
            nice = {"templates": "Конструктор PDF", "history": "История", "settings": "Настройки"}
            lbl = (nice.get(active) or next((l for k, l, h, ic in MENU if k == active), "")).replace("|", " · ")
            crumbs = f'<a href="/">Главная</a> &rsaquo; <b>{lbl}</b>' if lbl else ""
    crumbs_bar = (f'<div class="crumb-bar" style="border-top:1px solid #EDF3EF;'
                  f'font-size:12.5px;line-height:1.4;color:#6B7C70">'
                  f'<div class="wrap" style="padding-top:4px;padding-bottom:5px">{crumbs}</div>'
                  f'</div>') if crumbs else ""

    def _inline_css(name: str) -> str:
        """Вставляем стили прямо в страницу.

        На удалённом канале каждый отдельный запрос — это лишняя задержка, а
        стилей было четыре (base + стиль раздела + токены + оформление). Теперь
        один ответ вместо пяти.
        """
        import pathlib as _pl
        root = _pl.Path("/opt/wolf_v2/blocks/static/css")
        chunks = []
        for fname in ("base.css", "%s.css" % (name or "base"), "wolf-tokens.css", "wolf-skin.css"):
            f = root / fname
            try:
                st = f.stat()
                key = "%s|%s" % (f, int(st.st_mtime))
                cached = _CSS_MEM.get(key)
                if cached is None:
                    cached = _minify_css(f.read_text(encoding="utf-8"))
                    _CSS_MEM.clear()          # держим в памяти только актуальные версии
                    _CSS_MEM[key] = cached
                chunks.append(cached)
            except Exception:
                continue
        return "<style>%s</style>" % "\n".join(chunks)

    def _logo_data_uri() -> str:
        """Логотип вшиваем в страницу: это ещё один запрос на ровном месте."""
        import base64 as _b64
        import pathlib as _pl
        try:
            raw = _pl.Path("/opt/wolf_v2/data/branding/logo-small.jpg").read_bytes()
        except Exception:
            return "/branding/logo-small.jpg?v=1"
        return "data:image/jpeg;base64," + _b64.b64encode(raw).decode("ascii")

    _logo = _logo_data_uri()
    # Код интерфейса — отдельными файлами с версией: браузер держит их в кэше,
    # и при повторных заходах страница приходит только с данными заявки.
    # ВАЖНО: стили подключаем в проверенном порядке (base → раздел → токены →
    # оформление). Общий бандл всех CSS подряд ломал каскад: стили чужих
    # разделов подмешивались на каждую страницу. Не возвращать, пока бандл не
    # будет собираться по разделам.
    _head_assets = _inline_css(active)
    _tail_assets = "<script>%s</script>" % JS
    if False:                                # прежняя ветка с бандлом — отключена
        pass
    html = f"""<!doctype html><html lang="ru" class="is-booting"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#1F6BFF">
<link rel="icon" type="image/png" href="/branding/logo-small.png?v=1">
<title>{title} · Wolf AutoDoc</title>
<style>
/* Заставка на время загрузки: страница показывается целиком, без «прыжка»
   неоформленного текста, пока не применены стили и не построена графика. */
#boot-preloader{{position:fixed;inset:0;z-index:9000;background:#F1F5F3;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:14px;color:#0F6E63;
  font:600 14px/1 -apple-system,system-ui,"Segoe UI",sans-serif;transition:opacity .28s ease}}
html:not(.is-booting) #boot-preloader{{opacity:0;visibility:hidden}}
#boot-spinner{{width:46px;height:46px;border:4px solid #CFE3DC;border-top-color:#0F6E63;border-radius:50%;
  animation:bootspin .9s linear infinite}}
@keyframes bootspin{{to{{transform:rotate(360deg)}}}}
html.is-booting body>*:not(#boot-preloader){{visibility:hidden}}
@media (prefers-reduced-motion:reduce){{#boot-spinner{{animation-duration:2.4s}}}}
</style>{_head_assets}</head><body>
<div id="boot-preloader" role="status" aria-live="polite">
  <div id="boot-spinner"></div>
  <div>Загружаю страницу…</div>
</div>
<div class="topbar">
  <div class="topbar-row">
    <button type="button" class="burger" data-burger aria-label="меню"><span></span></button>
    <a class="brand-pill" href="/" title="На главную"><span class="logo"><img src="{_logo}" alt="Wolf AutoDoc" width="32" height="32"></span><b>Wolf AutoDoc</b></a>
    <span class="topbar-date">{date_label}</span>
    <span class="topbar-user">{_user_label()}</span>
  </div>
  {topbar}
  {crumbs_bar}
</div>
<main class="wrap">{flash_messages()}{body}</main>
<div class="drawer" id="drawer"><div class="panel">
  <div class="head"><span class="logo">🐺</span><b>Wolf AutoDoc</b>
    <button class="close" onclick="closeDrawer()" aria-label="закрыть">✕</button></div>
  <nav>{''.join(drawer_links)}</nav>
  <div class="spacer"></div>{who}
</div></div>
{_tail_assets}
<script>
/* Снимаем заставку, когда страница полностью загружена (стили, шрифты, картинки),
   плюс страховка на случай, если что-то не загрузится. */
(function(){{
  var done=false;
  function off(){{
    if(done) return; done=true;
    var el=document.getElementById('boot-preloader');
    document.documentElement.classList.remove('is-booting');
    if(el) setTimeout(function(){{ el.remove(); }}, 400);
  }}
  if(document.readyState==='complete') setTimeout(off, 90);
  else window.addEventListener('load', function(){{ setTimeout(off, 90); }});
  setTimeout(off, 6000);
}})();
</script></body></html>"""
    # Одиночные суррогаты (0xD800–0xDFFF) в HTML ломали ВСЮ страницу: werkzeug не может
    # закодировать их в utf-8, и админка отдавала 500 вместо заявки. Данные приходят из
    # разных источников (фото, тексты клиентов, парсеры) — вычищаем и записываем след в лог.
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in html):
        import logging as _log
        _i = next(i for i, ch in enumerate(html) if 0xD800 <= ord(ch) <= 0xDFFF)
        _log.getLogger("wolf").warning("в HTML найдены суррогаты (позиция %d): %r",
                                       _i, html[max(0, _i - 160):_i + 40])
        html = "".join(ch for ch in html if not (0xD800 <= ord(ch) <= 0xDFFF))
    resp = Response(html, mimetype="text/html; charset=utf-8")
    # Страница отдаётся с проверкой свежести: если браузер уже видел точно
    # такую же страницу, сервер отвечает «не изменилось» (304) — без тела.
    # При любой правке данных отпечаток меняется, и страница приходит заново.
    try:
        import hashlib as _hl2
        etag = '"%s"' % _hl2.sha1(html.encode("utf-8")).hexdigest()[:20]
        resp.headers["ETag"] = etag
        if request.headers.get("If-None-Match") == etag:
            return Response(status=304)
        resp.headers["Cache-Control"] = "no-cache"
    except Exception:
        resp.headers["Cache-Control"] = "no-store"
    return resp
