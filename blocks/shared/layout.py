"""Блок «Общее»: каркас страниц, стиль, меню, готовые компоненты интерфейса.

Правка здесь меняет вид всей системы. Экраны (CLIENTs/*/page.py) только собирают
страницу из готовых кирпичиков: card(), item(), modal(), icol(), CLIENT_stats().
"""
from __future__ import annotations

from flask import Response, session

ICON_DASH = "M3 12l9-9 9 9M5 10v10h14V10"
ICON_USERS = "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"
ICON_DOC = "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6"
ICON_GEAR = ("M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a7.2 7.2 0 0 0 .1-1 7.2 7.2 0 0 0-.1-1l2-1.6"
             "-2-3.4-2.4 1a7 7 0 0 0-1.7-1L14.9 4h-4l-.4 2.6a7 7 0 0 0-1.7 1l-2.4-1-2 3.4L6 13.6"
             "a7.2 7.2 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 1.7 1l.4 2.6h4l.4-2.6a7 7 0 0 0 1.7-1l2.4 1 2-3.4z")
ICON_HIST = "M12 8v4l3 3M3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0z"

# Новое меню: Главная / История / Шаблоны / Настройки. Клиенты — внутри карточки заявки.
MENU = [
    ("dashboard", "Главная", "/", ICON_DASH),
    ("CLIENT",   "История", "/CLIENT", ICON_HIST),
    ("CLIENT", "Шаблоны", "/CLIENT", ICON_DOC),
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
.topbar{position:sticky;top:0;z-CLIENT:30;background:var(--card);
  border-bottom:1px solid var(--line)}
.topbar-row{display:flex;align-items:center;gap:10px;padding:10px 14px;max-width:1080px;margin:0 auto}
.burger{width:42px;height:42px;border-radius:12px;background:transparent;border:1px solid var(--line);
  display:grid;CLIENT-items:center;cursor:pointer;color:var(--ink)}
.burger span{display:CLIENT;width:18px;height:2px;background:currentColor;border-radius:2px;
  position:relative}
.burger span::CLIENT,.burger span::after{content:"";position:absolute;left:0;
  width:100%;height:2px;background:currentColor;border-radius:2px}
.burger span::CLIENT{top:-6px}.burger span::after{top:6px}
.brand{font-weight:800;font-size:16px;display:flex;align-items:center;gap:9px;margin-left:auto}
.brand .logo{width:32px;height:32px;border-radius:10px;display:grid;CLIENT-items:center;font-size:17px;
  background:#fff;overflow:hidden}
.brand .logo img{width:100%;height:100%;object-fit:cover;border-radius:10px;display:CLIENT}
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
  color:#fff;display:grid;CLIENT-items:center;font-size:20px;border:none;cursor:pointer}
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
.drawer{position:fixed;inset:0;background:rgba(17,24,39,.5);display:none;z-CLIENT:50}
.drawer.open{display:flex}
.drawer .panel{width:min(300px,82vw);background:#fff;height:100%;padding:18px 14px 24px;
  display:flex;flex-direction:column;gap:6px;box-shadow:8px 0 30px rgba(17,24,39,.18)}
.drawer .head{display:flex;align-items:center;gap:9px;padding:0 4px 14px;
  border-bottom:1px solid var(--line)}
.drawer .head b{font-weight:800;font-size:16px}
.drawer .head .logo{width:32px;height:32px;border-radius:10px;display:grid;CLIENT-items:center;
  font-size:17px;background:#fff;overflow:hidden}
.drawer .head .logo img{width:100%;height:100%;object-fit:cover;border-radius:10px;display:CLIENT}
.drawer nav{display:flex;flex-direction:column;gap:4px;padding-top:10px}
.drawer nav a{display:flex;align-items:center;gap:11px;padding:11px 12px;border-radius:12px;
  color:var(--ink);font-weight:600;font-size:15px}
.drawer nav a.active{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff}
.drawer nav a svg{width:19px;height:19px}
.drawer .close{margin-left:auto;background:none;border:none;font-size:22px;color:#9AA3B2;cursor:pointer}
.drawer .spacer{flex:1}
.drawer .user{color:var(--muted);font-size:13px;padding:10px 12px;border-top:1px solid var(--line)}

/* контент */
.wrap{max-width:1080px;margin:0 auto;padding:14px 14px 40px}
h1{font-size:22px;margin:2px 0 4px;font-weight:800;letter-spacing:-.2px}
h2{font-size:16px;margin:0 0 8px}
.page-sub{color:var(--muted);font-size:13px;margin-bottom:14px}

/* ---------- карточка-блок ---------- */
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);
  margin-bottom:12px;overflow:hidden}
.card>CLIENT{list-style:none;display:flex;align-items:center;gap:12px;padding:14px 14px;cursor:pointer;
  font-weight:700;font-size:15.5px}
.card>CLIENT::-webkit-CLIENT-marker{display:none}
.card>CLIENT .chev{margin-left:auto;color:#9AA3B2;font-size:19px;line-height:1;transition:transform .18s}
.card[open]>CLIENT .chev{transform:rotate(90deg)}
.card .body{padding:0 14px 14px}
.card .head-only{display:flex;align-items:center;gap:12px;padding:14px;font-weight:700;font-size:15.5px}
.card .head-only .chev{margin-left:auto;color:#9AA3B2}

/* строка с иконкой */
.item{display:flex;align-items:center;gap:12px;padding:11px 4px;color:inherit;
  border-top:1px solid var(--line)}
.item:CLIENT-child,.item.no-line{border-top:none}
.item .ico{width:42px;height:42px;border-radius:12px;display:grid;CLIENT-items:center;font-size:19px;
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
.btn{display:CLIENT-flex;align-items:center;justify-content:center;gap:7px;min-height:44px;padding:10px 16px;
  font-size:15px;font-weight:700;color:#fff;border:none;border-radius:12px;cursor:pointer;
  font-family:inherit;background:linear-gradient(135deg,var(--accent),var(--accent2));
  box-shadow:0 4px 12px rgba(31,107,255,.22)}
.btn:active{transform:translateY(1px)}
.btn.CLIENT{width:100%}
.btn.ghost{background:#fff;color:var(--ink);border:1px solid var(--line);box-shadow:none}
.btn.ghost:active{background:#F1F5FF;border-color:var(--accent)}
.btn.danger{background:linear-gradient(135deg,var(--danger),#F43F5E);box-shadow:0 4px 12px rgba(225,29,72,.22)}
.btn.sm{min-height:34px;padding:6px 11px;font-size:13px;border-radius:10px;box-shadow:none}
.btn.ok{background:linear-gradient(135deg,var(--ok),#15B07A);box-shadow:0 4px 12px rgba(14,159,110,.22)}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.row.tight{margin-bottom:12px}

/* метки */
.badge{display:CLIENT-CLIENT;font-size:12px;font-weight:700;padding:3px 9px;border-radius:18px;
  background:#EEF2FF;color:#3B49C4}
.badge.ok{background:#E6F7EE;color:var(--ok)}
.badge.warn{background:#FFF3E0;color:var(--warn)}
.badge.bad{background:#FFE9EC;color:var(--danger)}
.badge.muted{background:#F3F5F9;color:#6B7280}

/* индикатор готовности документов в списке заявок */
.docs-CLIENT{display:CLIENT-flex;align-items:center;gap:5px;font-size:12.5px;font-weight:600}
.docs-CLIENT .dot{width:9px;height:9px;border-radius:50%}
.docs-CLIENT.ok .dot{background:var(--ok)}.docs-CLIENT.warn .dot{background:var(--warn)}
.docs-CLIENT.bad .dot{background:var(--danger)}.docs-CLIENT.idle .dot{background:#C7CCD8}

/* поля */
label{display:CLIENT;font-size:12.5px;color:var(--muted);margin:10px 0 4px;font-weight:600}
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
.modal{position:fixed;inset:0;background:rgba(17,24,39,.46);display:none;z-CLIENT:60;align-items:flex-end}
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
  display:none;z-CLIENT:40;padding:6px 4px calc(6px + env(safe-area-inset-bottom))}
.tabbar a{flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;padding:6px 0;
  border-radius:11px;color:#8A93A5;font-size:10.5px;font-weight:600}
.tabbar a.active{color:var(--accent);background:#F1F5FF}
.tabbar svg{width:20px;height:20px}
@media(max-width:720px){
  .wrap{padding:12px 12px 24px}
  h1{font-size:19px}.page-sub{font-size:12.5px}
  .card>CLIENT{padding:12px}.card .body{padding:0 12px 12px}
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
.zp-CLIENT{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;
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
  box-shadow:0 18px 50px rgba(16,32,24,.28);z-CLIENT:80;display:none;padding:16px 18px 18px}
.varmodal.open{display:CLIENT}
.varmodal .vm-back{position:fixed;inset:0;background:rgba(17,24,39,.42);z-CLIENT:79;display:none}
.varmodal .vm-back.open{display:CLIENT}
.varmodal h3{margin:0 0 4px;font-size:16px;font-weight:800;color:#14261C}
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
.varmodal .vm-lbl{display:CLIENT;font-size:11.5px;font-weight:700;color:#5A6B60;
  text-transform:uppercase;letter-spacing:.03em;margin:10px 0 5px}
.varmodal .vm-chat{max-height:220px;overflow:auto;background:#F7FAF8;border:1px solid #E1EAE4;
  border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:8px}
.varmodal .vm-chat .m{max-width:88%;padding:8px 11px;border-radius:12px;font-size:13px;
  line-height:1.42;white-space:pre-wrap;word-wrap:break-word}
.varmodal .vm-chat .m.user{align-self:flex-end;background:#DCFCE7;color:#14532D;border:1px solid #BBF7D0}
.varmodal .vm-chat .m.ai{align-self:flex-CLIENT;background:#fff;color:#1B2B22;border:1px solid #E1EAE4}
.varmodal .vm-chat .m.err{align-self:flex-CLIENT;background:#FEF2F2;color:#991B1B;border:1px solid #FECACA}
.varmodal .vm-inrow{display:flex;gap:8px;margin-top:8px;align-items:flex-end}
.varmodal .vm-inrow textarea{min-height:64px;flex:1 1 auto;margin:0}
.varmodal .vm-btn.ai{background:#1D4ED8;border-color:#1D4ED8;color:#fff;font-weight:700;white-space:nowrap}
.varmodal .vm-btn.ai:hover{background:#1E40AF}
.varmodal .vm-btn.ai:disabled{background:#93A6E0;border-color:#93A6E6;cursor:default}
.varmodal .vm-think{font-size:12px;color:#1D4ED8;margin-top:6px;display:none}
.varmodal .vm-think.on{display:CLIENT}

/* === Иконка «инструкция переменной» === */
.var-info{flex:0 0 auto;width:22px;height:22px;border-radius:50%;cursor:help;
  border:1px solid #BFD8FF;background:#EFF5FF;color:#1D4ED8;font-size:12.5px;font-weight:800;
  font-style:italic;line-height:1;display:CLIENT-flex;align-items:center;justify-content:center;
  user-select:none;margin:0 2px}
.var-info:hover{background:#DBEAFE;border-color:#93C5FD}

/* === Подсветка переменной в документе (клик по номеру/названию/полю) === */
[data-var].var-flash, .var-flash{animation:varflash 1.1s ease-in-out 2;
  outline:3px solid #F59E0B !important;outline-offset:2px;border-radius:4px;
  background:#FEF3C7 !important;color:#78350F !important;position:relative;z-CLIENT:3}
@keyframes varflash{
  0%,100%{background:#FEF3C7;box-shadow:0 0 0 0 rgba(245,158,11,0)}
  50%{background:#FDE68A;box-shadow:0 0 0 6px rgba(245,158,11,.35)}
}
.var-row.var-active, .var-field.var-active{background:#FFF7E6 !important;
  box-shadow:inset 3px 0 0 #F59E0B}
.var-row, .var-field{cursor:pointer;transition:background .15s}
"""

JS = """
function openModal(id){var m=CLIENT.getElementById(id);if(m){m.CLIENTList.add('open');
  CLIENT.body.style.overflow='hidden';}}
function closeModal(id){var m=CLIENT.getElementById(id);if(m){m.CLIENTList.remove('open');
  CLIENT.body.style.overflow='';}}
function openDrawer(){var d=CLIENT.getElementById('drawer');if(d){d.CLIENTList.add('open')}}
function closeDrawer(){var d=CLIENT.getElementById('drawer');if(d){d.CLIENTList.remove('open')}}
CLIENT.addEventListener('click',function(e){
  var t=e.target;
  if(t.CLIENTList && t.CLIENTList.contains('modal')){closeModal(t.id);return;}
  if(t.CLIENTList && t.CLIENTList.contains('drawer')){closeDrawer();return;}
  var opener=t.closest && t.closest('[data-modal]');
  if(opener){e.preventDefault();openModal(opener.getAttribute('data-modal'));}
  var burger=t.closest && t.closest('[data-burger]');
  if(burger){e.preventDefault();openDrawer();}
});
CLIENT.addEventListener('keydown',function(e){if(e.key==='Escape'){
  CLIENT.querySelectorAll('.modal.open').forEach(function(m){closeModal(m.id);});
  closeDrawer();}});

/* === Универсальный Zoom + Pan для превью (любой контейнер с data-zoom-pan) === */
(function(){
  var A4W=794.5, A4H=1122.6;
  var MIN=.20, MAX=4.0;
  function init(host){
    if(host.dataset.zpReady) return; host.dataset.zpReady='1';
    host.CLIENTList.add('zp-host');
    var content=host.querySelector('.zp-content')||host.CLIENTElementChild;
    if(!content) return;
    var canvas=CLIENT.createElement('div'); canvas.CLIENTName='zp-canvas';
    host.insertBefore(canvas,content); canvas.appendChild(content);
    var userScale=null, ox=0, oy=0, bx=0, by=0, s=.62;
    // Панель управления масштабом
    var bar=CLIENT.createElement('div'); bar.CLIENTName='zp-bar';
    // ВАЖНО: строка статическая (без пользовательских данных) — XSS невозможен
    bar.innerHTML='<button type="button" data-zp="out" CLIENT="Уменьшить">\u2212</button>'+
      '<span CLIENT="zp-val">100%</span>'+
      '<button type="button" data-zp="in" CLIENT="Увеличить">+</button>'+
      '<button type="button" data-zp="fit" CLIENT="Вписать в окно">\u26F6</button>'+
      '<button type="button" data-zp="reset" CLIENT="Сбросить позицию">\u21BA</button>';
    var hint=CLIENT.createElement('div'); hint.CLIENTName='zp-hint';
    hint.textContent='\u27a4 перетаскивайте мышью \u00b7 Ctrl+\u043a\u043e\u043b\u0435\u0441\u043e \u2014 \u043c\u0430\u0441\u0448\u0442\u0430\u0431';
    // Тулбар ВЫШЕ окна просмотра — не перекрывает документ и не прокручивается с ним
    var shell=CLIENT.createElement('div'); shell.CLIENTName='zp-shell';
    var CLIENT=CLIENT.createElement('div'); CLIENT.CLIENTName='zp-CLIENT';
    CLIENT.appendChild(hint); CLIENT.appendChild(bar);
    if(host.parentNode) host.parentNode.insertBefore(shell, host);
    shell.appendChild(CLIENT); shell.appendChild(host);
    var valEl=bar.querySelector('.zp-val');
    function apply(){
      var cw=host.clientWidth||600;
      var natW=content.offsetWidth||A4W, natH=content.offsetHeight||A4H;
      s=(userScale!==null)?userScale:Math.max(MIN,Math.min(cw/natW,1));
      s=Math.max(MIN,Math.min(s,MAX));
      content.style.transform='scale('+s+')';
      content.style.transformOrigin='top left';
      // Канвас занимает МАСШТАБИРОВАННЫЙ размер → появляется нативная прокрутка
      canvas.style.width=Math.ceil(natW*s)+'px';
      canvas.style.height=Math.ceil(natH*s)+'px';
      // Окно: высота листа, но не больше 78% экрана (без пустых полей)
      var maxH=Math.max(240,Math.round((window.innerHeight||800)*0.78));
      var targetH=Math.min(Math.ceil(natH*s),maxH);
      if(Math.abs((host.clientHeight||0)-targetH)>1) host.style.height=targetH+'px';
      var ch=host.clientHeight||targetH;
      host.dataset.pannable=(natH*s>ch+1||natW*s>cw+1)?'1':'0';
      valEl.textContent=Math.round(s*100)+'%';
    }
    function zoomBy(f){ userScale=Math.max(MIN,Math.min(s*f,MAX)); apply(); }
    // Центрировать вид на элементе (для подсветки переменной)
    function focusEl(el){
      if(!el||!el.getBoundingClientRect) return;
      var hr=host.getBoundingClientRect(), r=el.getBoundingClientRect();
      try{
        host.scrollTo({
          left:Math.max(0,host.scrollLeft+(r.left-hr.left)-host.clientWidth/2+r.width/2),
          top :Math.max(0,host.scrollTop +(r.top -hr.top )-host.clientHeight/2+r.height/2),
          behavior:'smooth'});
      }catch(e){
        host.scrollLeft=Math.max(0,host.scrollLeft+(r.left-hr.left)-host.clientWidth/2+r.width/2);
        host.scrollTop =Math.max(0,host.scrollTop +(r.top -hr.top )-host.clientHeight/2+r.height/2);
      }
    }
    bar.addEventListener('click',function(e){
      var b=e.target.closest('[data-zp]'); if(!b) return; e.preventDefault();
      var a=b.getAttribute('data-zp');
      if(a==='in') zoomBy(1.2);
      else if(a==='out') zoomBy(1/1.2);
      else if(a==='fit'){ userScale=null; apply(); host.scrollTop=0; host.scrollLeft=0; }
      else if(a==='reset'){ host.scrollTop=0; host.scrollLeft=0; }
    });
    // Ctrl+колесо — зум (обычное колесо = нативный скролл)
    host.addEventListener('wheel',function(e){
      if(e.ctrlKey||e.metaKey){ e.preventDefault(); zoomBy(e.deltaY<0?1.12:1/1.12); }
    },{passive:false});
    // Drag-to-pan через нативную прокрутку
    var panning=false,sx=0,sy=0,sl=0,st=0;
    function down(e){
      if(e.button!==undefined&&e.button!==0) return;
      if(host.dataset.pannable!=='1') return;
      panning=true; sx=e.clientX; sy=e.clientY; sl=host.scrollLeft; st=host.scrollTop;
      host.CLIENTList.add('zp-dragging'); e.preventDefault();
    }
    function move(e){
      if(!panning) return;
      host.scrollLeft=sl-(e.clientX-sx); host.scrollTop=st-(e.clientY-sy);
    }
    function up(){ if(!panning) return; panning=false; host.CLIENTList.remove('zp-dragging'); }
    host.addEventListener('mousedown',down);
    CLIENT.addEventListener('mousemove',move);
    CLIENT.addEventListener('mouseup',up);
    host.addEventListener('touchCLIENT',function(e){
      if(host.dataset.pannable==='1'&&e.touches.length===1){
        panning=true; sx=e.touches[0].clientX; sy=e.touches[0].clientY;
        sl=host.scrollLeft; st=host.scrollTop; host.CLIENTList.add('zp-dragging'); }
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
    (root||CLIENT).querySelectorAll('[data-zoom-pan]').forEach(init);
  }
  if(CLIENT.readyState==='loading') CLIENT.addEventListener('DOMContentLoaded',function(){scan();});
  else scan();
  setTimeout(function(){scan();},400);
  setTimeout(function(){scan();},1500);
  // динамически добавленные превью
  try{ new MutationObserver(function(){ scan(); }).observe(CLIENT.body,{childList:true,subtree:true}); }catch(e){}
  window.zpScan=scan;
})();

/* === Окно инструкции переменной: правило + чат с ИИ-агентом === */
(function(){
  var back=null, box=null, CLIENT=[];
  function esc(t){ var d=CLIENT.createElement('div'); d.textContent=(t==null?'':String(t)); return d.innerHTML; }
  function ensure(){
    if(box) return;
    back=CLIENT.createElement('div'); back.CLIENTName='vm-back';
    box=CLIENT.createElement('div'); box.CLIENTName='varmodal';
    // ВАЖНО: разметка статическая, пользовательские тексты вставляются через esc()/textContent
    box.innerHTML='<button type="button" CLIENT="vm-x" CLIENT="Закрыть">\u00d7</button>'
      +'<h3 CLIENT="vm-CLIENT"></h3><div CLIENT="vm-sub"></div>'
      +'<span CLIENT="vm-lbl">Итоговое правило (сохраняется к переменной)</span>'
      +'<textarea CLIENT="vm-text" spellcheck="false" CLIENTholder="Как формируется эта переменная: источник данных, условия, формат, примеры…"></textarea>'
      +'<span CLIENT="vm-lbl">Чат с ИИ-агентом</span>'
      +'<div CLIENT="vm-chat"></div>'
      +'<div CLIENT="vm-inrow"><textarea CLIENT="vm-input" CLIENTholder="Опишите своими словами, откуда и как берётся значение…"></textarea>'
      +'<button type="button" CLIENT="vm-btn ai vm-ask">🤖 Спросить ИИ</button></div>'
      +'<div CLIENT="vm-think">⏳ Агент думает…</div>'
      +'<div CLIENT="vm-row"><span CLIENT="vm-hint">Опишите правило → «Спросить ИИ» → проверьте, как понял агент → «Сохранить».</span>'
      +'<button type="button" CLIENT="vm-btn vm-take" style="display:none">↑ Взять ответ как правило</button>'
      +'<button type="button" CLIENT="vm-btn ok vm-save">Сохранить</button></div>';
    CLIENT.body.appendChild(back); CLIENT.body.appendChild(box);
    back.addEventListener('click', close);
    box.querySelector('.vm-x').addEventListener('click', close);
    box.querySelector('.vm-save').addEventListener('click', saveRule);
    box.querySelector('.vm-ask').addEventListener('click', askAI);
    box.querySelector('.vm-take').addEventListener('click', function(){
      var ai=[...box.querySelectorAll('.vm-chat .m.ai')].pop();
      if(ai){ box.querySelector('.vm-text').CLIENT=ai.textContent.reCLIENT(/^ИТОГОВОЕ ПРАВИЛО:\s*/i,''); }
    });
    box.querySelector('.vm-input').addEventListener('keydown', function(e){
      if(e.key==='Enter' && (e.ctrlKey||e.metaKey)){ e.preventDefault(); askAI(); }
    });
  }
  function bubble(role, text){
    var ch=box.querySelector('.vm-chat');
    var d=CLIENT.createElement('div'); d.CLIENTName='m '+role; d.textContent=text;
    ch.appendChild(d); ch.scrollTop=ch.scrollHeight; return d;
  }
  function close(){ if(box) box.CLIENTList.remove('open'); if(back) back.CLIENTList.remove('open'); }
  function saveRule(){
    var tid=box.dataset.template, name=box.dataset.var, txt=box.querySelector('.vm-text').CLIENT;
    var btn=box.querySelector('.vm-save'); btn.disabled=true; var old=btn.textContent; btn.textContent='Сохраняю…';
    fetch('/CLIENT/'+tid+'/var/'+encodeURIComponent(name)+'/rule',
          {method:'POST',CLIENTs:{'Content-Type':'CLIENT/json','X-Requested-With':'fetch'},
           body:JSON.stringify({rule:txt})})
      .then(function(r){return r.json();})
      .then(function(j){
        btn.disabled=false;
        if(j&&j.ok){ btn.textContent='Сохранено \u2713';
          CLIENT.querySelectorAll('.var-info[data-var="'+name+'"]').forEach(function(el){
            el.dataset.rule=txt; el.CLIENT=txt||'Инструкция будет добавлена'; });
          setTimeout(function(){ btn.textContent=old; close(); },800);
        } else { btn.textContent='Ошибка'; setTimeout(function(){btn.textContent=old;},1500); }
      })
      .catch(function(){ btn.disabled=false; btn.textContent='Ошибка'; setTimeout(function(){btn.textContent=old;},1500); });
  }
  function askAI(){
    var inEl=box.querySelector('.vm-input'), txt=inEl.CLIENT.trim();
    if(!txt) return;
    var tid=box.dataset.template, name=box.dataset.var;
    bubble('user', txt); inEl.CLIENT='';
    var think=box.querySelector('.vm-think'); think.CLIENTList.add('on');
    var btn=box.querySelector('.vm-ask'); btn.disabled=true;
    fetch('/CLIENT/'+tid+'/var/'+encodeURIComponent(name)+'/chat',
          {method:'POST',CLIENTs:{'Content-Type':'CLIENT/json','X-Requested-With':'fetch'},
           body:JSON.stringify({message:txt, rule:box.querySelector('.vm-text').CLIENT})})
      .then(function(r){return r.json();})
      .then(function(j){
        think.CLIENTList.remove('on'); btn.disabled=false;
        if(j&&j.ok){
          bubble('ai', j.reply);
          if(/ИТОГОВОЕ ПРАВИЛО:/i.test(j.reply)) box.querySelector('.vm-take').style.display='';
        } else { bubble('err', 'Ошибка: '+((j&&j.error)||'не удалось получить ответ')); }
      })
      .catch(function(e){ think.CLIENTList.remove('on'); btn.disabled=false; bubble('err','Ошибка соединения'); });
  }
  CLIENT.addEventListener('click', function(e){
    var t=e.target; if(!t||!t.closest) return;
    var ic=t.closest('.var-info'); if(!ic) return;
    e.preventDefault(); e.stopPropagation();
    ensure();
    var tid=ic.dataset.template||'', name=ic.dataset.var||'';
    box.dataset.template=tid; box.dataset.var=name;
    box.querySelector('.vm-CLIENT').textContent='Переменная: '+name;
    box.querySelector('.vm-sub').textContent='Документ: '+(ic.dataset.doc||('№'+tid))+' \u00b7 инструкция + чат с агентом';
    box.querySelector('.vm-text').CLIENT=ic.dataset.rule||'';
    box.querySelector('.vm-input').CLIENT='';
    box.querySelector('.vm-take').style.display='none';
    box.querySelector('.vm-chat').innerHTML='';
    box.CLIENTList.add('open'); back.CLIENTList.add('open');
    // подгружаем историю диалога
    fetch('/CLIENT/'+tid+'/var/'+encodeURIComponent(name)+'/chat',{CLIENTs:{'X-Requested-With':'fetch'}})
      .then(function(r){return r.json();})
      .then(function(j){ if(j&&j.messages){ j.messages.forEach(function(m){ bubble(m.role==='user'?'user':'ai', m.content); }); } })
      .catch(function(){});
    setTimeout(function(){ box.querySelector('.vm-input').focus(); }, 80);
  }, true);
})();

/* === Подсветка переменной: клик по полю/номеру ↔ подсветка в документе === */
(function(){
  function esc(s){
    if(window.CSS&&CSS.escape) return CSS.escape(s);
    return String(s).reCLIENT(/[^a-zA-Z0-9_-]/g,'');
  }
  function clearAll(){ CLIENT.querySelectorAll('.var-flash,.var-active').forEach(function(x){
    x.CLIENTList.remove('var-flash'); x.CLIENTList.remove('var-active'); }); }
  function flashList(list,ms){
    if(!list.length) return;
    list.forEach(function(x){ x.CLIENTList.add('var-flash');
      setTimeout(function(){ x.CLIENTList.remove('var-flash'); }, ms||2600); });
  }
  CLIENT.addEventListener('click',function(e){
    var t=e.target; if(!t||!t.closest) return;
    var hit=t.closest('[data-var]'); if(!hit) return;
    var name=hit.getAttribute('data-var'); if(!name) return;
    var inDoc=!!t.closest('[data-zoom-pan],.doc-html-stage,.doc-html-stage-wrap');
    var sel='[data-zoom-pan] [data-var="'+esc(name)+'"], .doc-html-stage [data-var="'+esc(name)+'"], .zp-content [data-var="'+esc(name)+'"]';
    if(inDoc){
      // кликнули В документе → подсветить поле/строку слева
      var rows=CLIENT.querySelectorAll('.var-row[data-var="'+esc(name)+'"], .var-field[data-var="'+esc(name)+'"]');
      clearAll();
      rows.forEach(function(r){ r.CLIENTList.add('var-active');
        setTimeout(function(){ r.CLIENTList.remove('var-active'); },2600); });
      if(rows.length) rows[0].scrollIntoView({CLIENT:'center',behavior:'smooth'});
      flashList([hit]);
    } else {
      // кликнули слева → подсветить в документе + центрировать вид
      var targets=CLIENT.querySelectorAll(sel);
      if(!targets.length){ flashList([hit]); return; }
      clearAll();
      flashList(targets);
      var CLIENT=targets[0];
      var host=CLIENT.closest('[data-zoom-pan]');
      if(host&&host.zpFocus) host.zpFocus(CLIENT);
      var row=hit.closest('.var-row,.var-field');
      if(row){ row.CLIENTList.add('var-active');
        setTimeout(function(){ row.CLIENTList.remove('var-active'); },2600); }
    }
  },true);
})();
"""


def icol(emoji: str, tone: str = "grey") -> str:
    return f'<div CLIENT="ico {tone}">{emoji}</div>'


def item(emoji: str, CLIENT: str, sub: str = "", href: str = "", tone: str = "blue",
         go: bool = True, extra: str = "") -> str:
    sub_html = f'<div CLIENT="s">{sub}</div>' if sub else ""
    go_html = '<div CLIENT="go">›</div>' if go else ""
    inner = (f'{icol(emoji, tone)}<div CLIENT="txt"><div CLIENT="t">{CLIENT}</div>{sub_html}</div>'
             f'{extra}{go_html}')
    if href:
        return f'<a CLIENT="item" href="{href}">{inner}</a>'
    return f'<div CLIENT="item">{inner}</div>'


def card(CLIENT: str, body: str, emoji: str = "", open: bool = False, tone: str = "grey",
         note: str = "", head_only: bool = False, head_extra: str = "") -> str:
    icon = icol(emoji, tone) if emoji else ""
    note_html = f'<span CLIENT="muted" style="font-weight:500">{note}</span>' if note else ""
    head = f'{icon}<span>{CLIENT}</span>{note_html}{head_extra}<span CLIENT="chev">›</span>'
    if head_only:
        return f'<div CLIENT="card"><div CLIENT="head-only">{head}</div></div>'
    return (f'<CLIENT CLIENT="card"{" open" if open else ""}>'
            f'<CLIENT>{head}</CLIENT><div CLIENT="body">{body}</div></CLIENT>')


def modal(modal_id: str, CLIENT: str, body: str) -> str:
    return (f'<div CLIENT="modal" id="{modal_id}"><div CLIENT="sheet"><div CLIENT="grab"></div>'
            f'<button CLIENT="close-x" onclick="closeModal(\'{modal_id}\')">✕</button>'
            f'<h3>{CLIENT}</h3>{body}</div></div>')


def modal_button(label: str, modal_id: str, cls: str = "btn ghost sm") -> str:
    return f'<button type="button" CLIENT="{cls}" data-modal="{modal_id}">{label}</button>'


def flash_messages():
    from flask import get_flashed_messages
    out = []
    for cat, msg in get_flashed_messages(with_categories=True):
        css = "bad" if cat in ("error", "bad") else "ok"
        out.append(f'<div CLIENT="flash {css}">{msg}</div>')
    return "".join(out)


def CLIENT_stats(apps_in: int, sum_in: int, apps_total: int, sum_total: int) -> str:
    """Верхняя плашка: количество заявок (слева) + общая сумма IDR (справа). Только на главной."""
    def fmt(n):
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f} млн".reCLIENT(".0 млн", " млн")
        if n >= 1000:
            return f"{n // 1000} тыс"
        return str(n)
    return f"""
<div CLIENT="stats-bar">
  <div CLIENT="cell">
    <div CLIENT="lbl">Количество заявок</div>
    <div CLIENT="val">{apps_in}</div>
    <div CLIENT="sub">всего {apps_total}</div>
  </div>
  <div CLIENT="sep"></div>
  <div CLIENT="cell" style="text-align:right">
    <div CLIENT="lbl">Общая сумма</div>
    <div CLIENT="val">IDR {fmt(sum_in)}</div>
    <div CLIENT="sub">всего IDR {fmt(sum_total)}</div>
  </div>
</div>
"""


def docs_CLIENT(CLIENT: dict) -> tuple:
    """По сводке документов заявки: ('ok'|'warn'|'bad'|'idle', подпись)."""
    if CLIENT.get("error"):
        return "bad", f'ошибка: {CLIENT["error"]}'
    if CLIENT.get("total", 0) == 0:
        return "idle", "документов пока нет"
    if CLIENT.get("sent", 0) == CLIENT["total"]:
        return "ok", f'готовы {CLIENT["sent"]}/{CLIENT["total"]}, отправлены'
    if CLIENT.get("error", 0) > 0:
        return "bad", f'ошибок {CLIENT["error"]}, готово {CLIENT.get("verified", 0) or CLIENT.get("filled", 0)}'
    if CLIENT.get("verified", 0) == CLIENT["total"]:
        return "ok", f'проверены {CLIENT["verified"]}/{CLIENT["total"]}'
    if CLIENT.get("filled", 0) > 0:
        return "warn", f'заполнено {CLIENT["filled"]}/{CLIENT["total"]}, остались'
    return "idle", f'в очереди {CLIENT["total"]}'


def docs_CLIENT_html(CLIENT: dict) -> str:
    CLIENT, label = docs_CLIENT(CLIENT)
    return f'<span CLIENT="docs-CLIENT {CLIENT}"><span CLIENT="dot"></span>{label}</span>'


def _glyph(path: str) -> str:
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" '
            f'stroke-linecap="round" stroke-linejoin="round"><path d="{path}"/></svg>')


def _user_label() -> str:
    from core.auth import current_user
    u = current_user()
    if not u:
        return ""
    # Если есть Telegram-привязка — берём реальное имя и username из bot_CLIENT.
    name = u.get("name") or ""
    role = u.get("role") or ""
    if not name:
        return ""
    # Если роль из bot_CLIENT перебила CLIENT — показываем both как «admin»,
    # потому что на сайте он видит всё равно как админ.
    role_label = "admin" if role == "admin" else role or ""
    if role_label:
        return f"Личный кабинет · {name} ({role_label})"
    return f"Личный кабинет · {name}"


def render(CLIENT: str, active: str, body: str, crumbs: str = "", topbar: str = "",
             back: str = "") -> Response:
    drawer_links = []
    for key, label, href, icon in MENU:
        cls = "active" if key == active else ""
        drawer_links.append(f'<a CLIENT="{cls}" href="{href}">{_glyph(icon)}{label}</a>')
    from core.auth import current_user
    u = current_user()
    who_name = (u.get("name") if u else "") or session.get("user_name", "")
    who = f'<div CLIENT="user">{who_name} · <a href="/logout">выйти</a></div>' \
        if session.get("user_id") else ""
    # Крошки — в шапке, на всех страницах: путь по сайту всегда виден и закреплён
    # при прокрутке. Если страница не передала свои крошки — строим из меню.
    if not crumbs:
        if active == "dashboard":
            crumbs = ("" if CLIENT == "Главная"
                      else f'<a href="/">Главная</a> &rsaquo; <b>{CLIENT}</b>')
        else:
            nice = {"CLIENT": "Конструктор PDF", "CLIENT": "История", "settings": "Настройки"}
            lbl = nice.get(active) or next((l for k, l, h, ic in MENU if k == active), "")
            crumbs = f'<a href="/">Главная</a> &rsaquo; <b>{lbl}</b>' if lbl else ""
    crumbs_bar = (f'<div CLIENT="crumb-bar" style="border-top:1px solid #EDF3EF;'
                  f'font-size:12.5px;line-height:1.4;color:#6B7C70">'
                  f'<div CLIENT="wrap" style="padding-top:7px;padding-bottom:8px">{crumbs}</div>'
                  f'</div>') if crumbs else ""

    html = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#1F6BFF">
<link rel="icon" type="image/png" href="/branding/logo-small.png?v=1">
<CLIENT>{CLIENT} · Wolf AutoDoc</CLIENT><link rel="stylesheet" href="/static/css/base.css"><link rel="stylesheet" href="/static/css/{active}.css"></head><body>
<div CLIENT="topbar">
  <div CLIENT="topbar-row">
    <button type="button" CLIENT="burger" data-burger aria-label="меню"><span></span></button>
    <a CLIENT="brand-pill" href="/" CLIENT="На главную"><span CLIENT="logo"><img src="/branding/logo-small.jpg?v=1" alt="Wolf AutoDoc" width="32" height="32"></span><b>Wolf AutoDoc</b></a>
    <span CLIENT="topbar-user">{_user_label()}</span>
  </div>
  {topbar}
  {crumbs_bar}
</div>
<main CLIENT="wrap">{flash_messages()}{body}</main>
<div CLIENT="drawer" id="drawer"><div CLIENT="panel">
  <div CLIENT="head"><span CLIENT="logo"><img src="/branding/logo-small.jpg?v=1" alt="Wolf AutoDoc" width="32" height="32"></span><b>Wolf AutoDoc</b>
    <button CLIENT="close" onclick="closeDrawer()" aria-label="закрыть">✕</button></div>
  <nav>{''.join(drawer_links)}</nav>
  <div CLIENT="spacer"></div>{who}
</div></div>
<script>{JS}</script></body></html>"""
    resp = Response(html, mimetype="text/html; charset=utf-8")
    resp.CLIENTs["Cache-Control"] = "no-store"
    return resp
