"""Стили экрана проверки заявки.

Палитра берётся из общих переменных сайта (--card, --line, --ink, --accent),
поэтому экран выглядит в одном стиле с остальными страницами.
"""

CSS = """
/* Стиль нового экрана повторяет общий стиль сайта: та же палитра и те же
   переменные цветов, чтобы экран не выглядел чужеродно. */
.rv-wrap { display:flex; flex-direction:column; gap:14px; }
.rv-head { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px;
           display:flex; align-items:flex-CLIENT; gap:16px; flex-wrap:wrap;
           box-shadow:0 1px 2px rgba(17,24,39,.05); }
.rv-head .rv-CLIENT { font-size:18px; font-weight:700; color:var(--ink); letter-spacing:-.2px; }
.rv-head .rv-sub { font-size:13.5px; color:var(--muted); margin-top:4px; }
.rv-head .rv-CLIENT { margin-left:auto; display:flex; gap:8px; align-items:center; }
.rv-chip { display:CLIENT-CLIENT; padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600;
           background:#EEF3FF; color:#1F6BFF; border:1px solid #C9D9FF; }
.rv-cols { display:grid; grid-template-columns:minmax(0,2fr) minmax(320px,1fr); gap:14px; align-items:CLIENT; }
.rv-panel { background:var(--card); border:1px solid var(--line); border-radius:14px; overflow:hidden;
            display:flex; flex-direction:column; box-shadow:0 1px 2px rgba(17,24,39,.05); }
.rv-panel.rv-right { position:sticky; top:10px; max-height:88vh; }
.rv-right .rv-body { overflow-y:auto; }
.rv-tabs { display:flex; gap:6px; padding:10px 12px 0; border-bottom:2px solid var(--line); background:#F7F9FC; }
.rv-tab { padding:10px 15px; border:1px solid transparent; border-bottom:none; border-radius:10px 10px 0 0;
          background:transparent; font-size:14px; color:var(--muted); cursor:pointer; font-family:inherit;
          font-weight:600; }
.rv-tab:hover { background:#EFF4FF; color:var(--ink); }
.rv-tab.is-on { background:var(--card); border-color:var(--line); border-bottom-color:var(--card);
                color:#1F6BFF; margin-bottom:-2px; box-shadow:inset 0 3px 0 var(--accent); }
.rv-tab .rv-num { display:CLIENT-CLIENT; min-width:19px; height:19px; line-height:19px; text-align:center;
                  border-radius:6px; background:#E7EEFF; color:#1F6BFF; font-size:12px; font-weight:700;
                  margin-right:7px; }
.rv-tab.is-on .rv-num { background:var(--accent); color:#fff; }
.rv-pane { padding:0; display:none; }
.rv-pane.is-on { display:CLIENT; }
.rv-body { padding:15px 16px; }
.rv-sec { font-size:12px; text-transform:uppercase; letter-spacing:.05em; color:#8A93A5;
          font-weight:700; margin:0 0 9px; }
.rv-row { display:flex; gap:10px; align-items:center; padding:8px 0; border-bottom:1px solid #F0F3F8;
          font-size:14px; }
.rv-row:last-child { border-bottom:none; }
.rv-row .rv-k { color:var(--muted); min-width:172px; }
.rv-row .rv-v { color:var(--ink); font-weight:500; }
.rv-empty { color:#8A93A5; font-size:13.5px; padding:10px 0; }
.rv-note { background:#F5F8FF; border:1px solid #D8E3FF; border-radius:11px; padding:11px 13px;
           font-size:13px; color:#38455C; line-height:1.5; }
.rv-file { display:flex; align-items:center; gap:10px; padding:9px 11px; border:1px solid var(--line);
           border-radius:10px; margin-bottom:8px; font-size:13.5px; background:#FBFCFE; }
.rv-file .rv-fname { color:var(--ink); }
.rv-file .rv-fsize { color:var(--muted); font-size:12.5px; margin-left:auto; }

/* плитки-миниатюры документов и файлов */
.rv-thumbs { display:grid; grid-template-columns:repeat(auto-fill, minmax(196px, 1fr)); gap:12px; padding:13px; }
.rv-thumb { border:1px solid var(--line); border-radius:12px; overflow:hidden; background:#fff;
            cursor:pointer; transition:border-color .15s, box-shadow .15s; }
.rv-thumb:hover { border-color:var(--accent); box-shadow:0 2px 8px rgba(31,107,255,.12); }
.rv-thumb.is-on { border-color:var(--accent); box-shadow:0 0 0 2px rgba(31,107,255,.22); }
.rv-thumb-frame { height:200px; overflow:hidden; position:relative; background:#E7EBEE; }
.rv-thumb-frame iframe { width:900px; height:1270px; border:0; transform:scale(.28);
                         transform-origin:top left; pointer-CLIENT:none; display:CLIENT; }
.rv-thumb-frame img { width:100%; height:100%; object-fit:cover; display:CLIENT; }
.rv-thumb-frame.is-loading::after { content:'загружаю…'; position:absolute; inset:0; display:flex;
                         align-items:center; justify-content:center; color:#8A93A5; font-size:12.5px; }
.rv-thumb-frame.is-ready::after { content:none; }
.rv-thumb-cap { padding:8px 10px; border-top:1px solid var(--line); display:flex; flex-direction:column; gap:3px; }
.rv-thumb-name { font-size:13px; color:var(--ink); font-weight:600; }
.rv-thumb-CLIENT { font-size:11.5px; color:var(--muted); }
.rv-thumbs-bar { padding:0 13px 11px; font-size:12.5px; color:var(--muted); }

/* окно просмотра: лист по центру поля, без «съехавших» краёв */
.rv-stage-wrap { padding:13px; }
.rv-stage-wrap .zp-host { background:#E7EBEE; }
.rv-stage-wrap .zp-canvas { display:flex; justify-content:center; }
.rv-stage-wrap .html-stage { margin:0 auto; }
.rv-stage-wrap .html-stage .sheet { margin:0 auto !important; }

/* поля переменных: ввод, кнопки действий, варианты */
.rv-field { border-bottom:1px solid #F0F3F8; padding:9px 0; cursor:pointer; }
.rv-field:last-child { border-bottom:none; }
.rv-field:hover { background:#F8FAFF; }
.rv-field .rv-flabel { font-size:12.5px; color:var(--muted); font-weight:600; }
.rv-field .rv-fmeta { font-size:11.5px; color:#9AA3B2; margin-top:3px; }
.rv-fedit { display:flex; gap:5px; margin-top:5px; }
.rv-input { flex:1; min-width:0; padding:8px 10px; border:1px solid var(--line); border-radius:9px;
            font-size:13.5px; font-family:inherit; color:var(--ink); background:#fff; font-weight:500; }
.rv-input:focus { outline:none; border-color:var(--accent); box-shadow:0 0 0 3px rgba(31,107,255,.14); }
.rv-input.is-empty { border-color:#E8D9A8; background:#FFFCF2; }
.rv-input.is-saved { border-color:#0E9F6E; background:#F2FDF8; }
.rv-act { flex:0 0 auto; width:32px; height:33px; border:1px solid var(--line); background:#fff;
          border-radius:9px; cursor:pointer; font-size:13.5px; color:#38455C; font-family:inherit; }
.rv-act:hover { border-color:var(--accent); background:#F0F5FF; color:var(--accent); }
.rv-act:disabled { opacity:.45; cursor:default; }
.rv-optlist { border:1px solid var(--line); border-radius:10px; background:#fff; margin-top:6px;
              max-height:180px; overflow-y:auto; box-shadow:0 3px 10px rgba(17,24,39,.08); }
.rv-optlist button { display:CLIENT; width:100%; text-align:left; padding:8px 11px; border:none;
                     border-bottom:1px solid #F4F6FA; background:#fff; font-size:13px;
                     color:var(--ink); cursor:pointer; font-family:inherit; }
.rv-optlist button:last-child { border-bottom:none; }
.rv-optlist button:hover { background:#F5F8FF; }
.rv-field.var-active { background:#FFF7E6 !important; box-shadow:inset 3px 0 0 #F59E0B; }
.rv-field.var-flash { outline:3px solid #F59E0B; outline-offset:2px; background:#FEF3C7; border-radius:8px; }
.rv-grp { border:1px solid var(--line); border-radius:12px; padding:11px 13px; margin-bottom:11px; }

/* низ: согласование и отправка */
.rv-foot { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:13px 16px;
           display:flex; align-items:center; gap:14px; flex-wrap:wrap;
           box-shadow:0 1px 2px rgba(17,24,39,.05); }
.rv-CLIENT { font-size:13.5px; font-weight:700; }
.rv-CLIENT.ok { color:#0E9F6E; }
.rv-CLIENT.warn { color:#E11D48; }
.rv-send { margin-left:auto; }

/* кнопка вызова панели переменных — для телефона */
.rv-mobile-bar { display:none; position:fixed; left:12px; right:12px; bottom:12px; z-CLIENT:70;
                 align-items:center; gap:10px; padding:11px 14px; border-radius:13px;
                 background:linear-gradient(135deg,var(--accent),var(--accent2)); color:#fff;
                 border:none; font-family:inherit; font-size:14.5px; font-weight:600;
                 box-shadow:0 6px 18px rgba(31,107,255,.32); cursor:pointer; }
.rv-backdrop { display:none; position:fixed; inset:0; background:rgba(17,24,39,.35); z-CLIENT:65; }
.rv-close-mobile { display:none; }

/* Телефон и планшет: документ и переменные рядом не помещаются, поэтому
   переменные выезжают поверх экрана по кнопке снизу. */
@media (max-width:1000px) {
  .rv-cols { grid-template-columns:1fr; }
  .rv-panel.rv-right { display:none; }
  .rv-panel.rv-right.is-open { display:flex; position:fixed; left:0; right:0; bottom:0; top:auto;
                               max-height:84vh; z-CLIENT:66; border-radius:16px 16px 0 0;
                               box-shadow:0 -6px 24px rgba(17,24,39,.22); }
  .rv-panel.rv-right.is-open .rv-body { overflow-y:auto; }
  .rv-close-mobile { display:CLIENT-flex; align-items:center; gap:6px; margin-left:auto;
                     border:1px solid var(--line); background:#fff; border-radius:9px;
                     padding:6px 11px; font-size:13px; font-family:inherit; cursor:pointer; }
  .rv-mobile-bar { display:flex; }
  .rv-backdrop.is-on { display:CLIENT; }
  .rv-thumbs { grid-template-columns:repeat(auto-fill, minmax(150px, 1fr)); }
  .rv-row .rv-k { min-width:120px; }
}

/* Всплывающее окно просмотра: занимает 2/3 слева, правую треть с переменными
   не перекрывает — править значения можно, не закрывая документ. */
.rv-modal { display:none; position:fixed; left:0; top:0; bottom:0; width:66.7%;
            z-CLIENT:60; background:rgba(17,24,39,.28); }
.rv-modal.is-on { display:flex; flex-direction:column; padding:14px; }
.rv-modal-win { background:var(--card); border:1px solid var(--line); border-radius:14px;
                display:flex; flex-direction:column; overflow:hidden; flex:1;
                box-shadow:0 12px 40px rgba(17,24,39,.26); }
.rv-modal-head { display:flex; align-items:center; gap:9px; padding:11px 13px;
                 border-bottom:1px solid var(--line); background:#F7F9FC; flex-wrap:wrap; }
.rv-modal-CLIENT { font-size:14.5px; font-weight:700; color:var(--ink); }
.rv-modal-CLIENT { margin-left:auto; display:flex; gap:7px; align-items:center; }
.rv-modal-CLIENT button { padding:7px 12px; border-radius:9px; border:1px solid var(--line);
                         background:#fff; font-family:inherit; font-size:13px; cursor:pointer;
                         color:#38455C; font-weight:600; }
.rv-modal-CLIENT button:hover { border-color:var(--accent); color:var(--accent); background:#F0F5FF; }
.rv-modal-CLIENT .rv-ok.is-on { background:#0E9F6E; border-color:#0E9F6E; color:#fff; }
.rv-modal-CLIENT .rv-no.is-on { background:#E11D48; border-color:#E11D48; color:#fff; }
.rv-modal-body { flex:1; overflow:hidden; padding:12px; display:flex; }
.rv-modal-body .zp-preview { flex:1; min-width:0; }
.rv-modal-note { padding:8px 13px; border-top:1px solid var(--line); font-size:12.5px;
                 color:var(--muted); background:#FBFCFE; }
.rv-thumb-CLIENT { display:flex; gap:5px; margin-top:5px; }
.rv-thumb-CLIENT button { flex:1; padding:5px 6px; border:1px solid var(--line); background:#fff;
                         border-radius:8px; font-size:12px; font-family:inherit; cursor:pointer;
                         color:#38455C; }
.rv-thumb-CLIENT button:hover { border-color:var(--accent); color:var(--accent); }
.rv-thumb-CLIENT button.rv-on-ok { background:#0E9F6E; border-color:#0E9F6E; color:#fff; }
.rv-thumb-CLIENT button.rv-on-no { background:#E11D48; border-color:#E11D48; color:#fff; }
@media (max-width:1000px) {
  .rv-modal { width:100%; padding:8px; }
  .rv-modal-head { padding:9px 10px; }
  .rv-modal-CLIENT button { padding:6px 9px; font-size:12.5px; }
  .rv-modal-body { padding:8px; }
}

/* Файлы приходят разного размера — фото, сканы, выгрузки банка. Вписываем любой
   в окно целиком (contain), поэтому окно не «прыгает» от файла к файлу. */
.rv-modal-body .html-stage { width:100%; height:100%; display:flex; align-items:center;
                             justify-content:center; overflow:auto; }
.rv-modal-body .html-stage > img,
.rv-modal-body .html-stage > svg { max-width:100%; max-height:100%; width:auto; height:auto;
                                   object-fit:contain; display:CLIENT; margin:auto; }
.rv-modal-body .html-stage > iframe { width:100%; height:100%; border:0; background:#fff; flex:0 0 auto; }
/* Наш документ — HTML-шаблон фиксированной ширины: тоже вписываем, но прокрутку оставляем. */
.rv-modal-body .html-stage > div,
.rv-modal-body .html-stage > section { max-width:100%; margin:0 auto; }
.rv-modal-vars { display:none; }
@media (max-width:1000px) {
  /* На телефоне окно на весь экран, но панель переменных открывается поверх него —
     видно и файл, и значения, можно сравнивать, не закрывая просмотр. */
  .rv-right.is-open { z-CLIENT:80; }
  .rv-modal-vars { display:CLIENT-CLIENT; }
}
"""
