"""Стили экрана проверки заявки.

Палитра берётся из общих переменных сайта (--card, --line, --ink, --accent),
поэтому экран выглядит в одном стиле с остальными страницами.
"""

CSS = """
/* Стиль нового экрана повторяет общий стиль сайта: та же палитра и те же
   переменные цветов, чтобы экран не выглядел чужеродно. */
.rv-wrap { display:flex; flex-direction:column; gap:14px;
            /* Карточка заявки исторически зелёная, остальной сайт — синий.
               Меняем палитру только внутри этого экрана. */
            --accent:#15803D; --accent-dark:#14663A; --line:#DCEEE2; }
.rv-head { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px;
           display:flex; align-items:flex-CLIENT; gap:16px; flex-wrap:wrap;
           box-shadow:0 1px 2px rgba(17,24,39,.05); }
.rv-head .rv-CLIENT { font-size:18px; font-weight:700; color:var(--ink); letter-spacing:-.2px; }
.rv-head .rv-sub { font-size:13.5px; color:var(--muted); margin-top:4px; }
.rv-head .rv-CLIENT { margin-left:auto; display:flex; gap:8px; align-items:center; }
.rv-chip { display:CLIENT-CLIENT; padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600;
           background:#DCFCE7; color:#15803D; border:1px solid #BFE0CB; }
.rv-cols { display:grid; grid-template-columns:minmax(0,2fr) minmax(320px,1fr); gap:14px;
            align-items:stretch; }
.rv-left { display:flex; flex-direction:column; gap:14px; min-width:0; }
.rv-panel { background:var(--card); border:1px solid var(--line); border-radius:14px; overflow:hidden;
            display:flex; flex-direction:column; box-shadow:0 1px 2px rgba(17,24,39,.05); }
.rv-panel.rv-right { position:sticky; top:8px; max-height:none;
                       height:calc(100vh - 20px); }
.rv-right .rv-body { overflow-y:auto; padding:12px 12px 18px; }
.rv-tabs { display:flex; gap:6px; padding:10px 12px 0; border-bottom:2px solid var(--line); background:#F4FAF6; }
.rv-tab { padding:10px 15px; border:1px solid transparent; border-bottom:none; border-radius:10px 10px 0 0;
          background:transparent; font-size:14px; color:var(--muted); cursor:pointer; font-family:inherit;
          font-weight:600; }
.rv-tab:hover { background:#E5F2EA; color:var(--ink); }
.rv-tab.is-on { background:var(--card); border-color:var(--line); border-bottom-color:var(--card);
                color:#15803D; margin-bottom:-2px; box-shadow:inset 0 3px 0 var(--accent); }
.rv-tab .rv-num { display:CLIENT-CLIENT; min-width:19px; height:19px; line-height:19px; text-align:center;
                  border-radius:6px; background:#DCFCE7; color:#15803D; font-size:12px; font-weight:700;
                  margin-right:7px; }
.rv-tab.is-on .rv-num { background:var(--accent); color:#fff; }
.rv-pane { padding:0; display:none; }
.rv-pane.is-on { display:CLIENT; }
.rv-body { padding:15px 16px; }
.rv-sec { font-size:12px; text-transform:uppercase; letter-spacing:.05em; color:#6B7C70;
          font-weight:700; margin:0 0 9px; }
.rv-row { display:flex; gap:10px; align-items:center; padding:8px 0; border-bottom:1px solid #EAF4EE;
          font-size:14px; }
.rv-row:last-child { border-bottom:none; }
.rv-row .rv-k { color:var(--muted); min-width:172px; }
.rv-row .rv-v { color:var(--ink); font-weight:500; }
.rv-empty { color:#6B7C70; font-size:13.5px; padding:10px 0; }
.rv-note { background:#F4FAF6; border:1px solid #DCEEE2; border-radius:11px; padding:11px 13px;
           font-size:13px; color:#38455C; line-height:1.5; }
.rv-file { display:flex; align-items:center; gap:10px; padding:9px 11px; border:1px solid var(--line);
           border-radius:10px; margin-bottom:8px; font-size:13.5px; background:#FBFDFC; }
.rv-file .rv-fname { color:var(--ink); }
.rv-file .rv-fsize { color:var(--muted); font-size:12.5px; margin-left:auto; }

/* плитки-миниатюры документов и файлов */
.rv-thumbs { display:grid; grid-template-columns:repeat(auto-fill, minmax(196px, 1fr)); gap:12px; padding:13px; }
.rv-thumb { border:1px solid var(--line); border-radius:12px; overflow:hidden; background:#fff;
            cursor:pointer; transition:border-color .15s, box-shadow .15s; }
.rv-thumb:hover { border-color:var(--accent); box-shadow:0 2px 8px rgba(21,128,61,.14); }
.rv-thumb.is-on { border-color:var(--accent); box-shadow:0 0 0 2px rgba(21,128,61,.24); }
.rv-thumb-frame { height:200px; overflow:hidden; position:relative; background:#E7EBEE; }
.rv-thumb-frame iframe { width:900px; height:1270px; border:0; transform:scale(.28);
                         transform-origin:top left; pointer-CLIENT:none; display:CLIENT; }
.rv-thumb-frame img { width:100%; height:100%; object-fit:cover; display:CLIENT; }
.rv-thumb-frame.is-loading::after { content:''; position:absolute; inset:0; margin:auto;
                         width:26px; height:26px; border-radius:50%; border:3px solid #DCEEE2;
                         border-top-color:#15803D; animation:rv-spin .9s linear infinite; }
.rv-thumb-frame.is-loading::CLIENT { content:'загружаю…'; position:absolute; left:0; right:0; bottom:10px;
                         text-align:center; color:#6B7C70; font-size:12px; }
.rv-thumb-frame.is-ready::after { content:none; }
.rv-thumb-cap { padding:8px 10px; border-top:1px solid var(--line); display:flex; flex-direction:column; gap:3px; }
.rv-thumb-name { font-size:13px; color:var(--ink); font-weight:600; display:flex;
                align-items:center; gap:6px; }
.rv-thumb-name .rv-tile-dot { margin-left:auto; flex:0 0 auto; }
.rv-thumb-CLIENT { font-size:11.5px; color:var(--muted); }
.rv-thumbs-bar { padding:0 13px 11px; font-size:12.5px; color:var(--muted); }

/* окно просмотра: лист по центру поля, без «съехавших» краёв */
.rv-stage-wrap { padding:13px; }
.rv-stage-wrap .zp-host { background:#E7EBEE; }
.rv-stage-wrap .zp-canvas { display:flex; justify-content:center; }
.rv-stage-wrap .html-stage { margin:0 auto; }
.rv-stage-wrap .html-stage .sheet { margin:0 auto !important; }

/* поля переменных: ввод, кнопки действий, варианты */
.rv-field { border-bottom:1px solid #EAF4EE; padding:9px 0; cursor:pointer; }
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
.rv-optlist button:hover { background:#F4FAF6; }
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
.rv-modal { display:none; position:fixed; left:0; top:0; bottom:0; width:calc(66.667% - 18px);
            z-CLIENT:60; background:rgba(17,24,39,.28); }
.rv-modal.is-on { display:flex; flex-direction:column; padding:14px; }
.rv-modal-win { background:var(--card); border:0; border-radius:16px;
                display:flex; flex-direction:column; overflow:hidden; flex:1;
                box-shadow:0 24px 70px rgba(16,24,32,.34), 0 6px 20px rgba(16,24,32,.18); }
.rv-modal-head { display:flex; align-items:center; gap:9px; padding:11px 13px;
                 border-bottom:1px solid var(--line); background:#F4FAF6; flex-wrap:wrap; }
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
                 color:var(--muted); background:#FBFDFC; }
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
.rv-modal-vars { display:none; }
@media (max-width:1000px) {
  /* На телефоне окно на весь экран, но панель переменных открывается поверх него —
     видно и файл, и значения, можно сравнивать, не закрывая просмотр. */
  .rv-right.is-open { z-CLIENT:80; }
  .rv-modal-vars { display:CLIENT-CLIENT; }
}

/* Заголовки этапов работы — один вид: номер в квадрате и название. */
.rv-stage { display:flex; align-items:center; gap:7px; font-size:14px; font-weight:700;
            color:#14663A; padding:11px 14px; border-bottom:2px solid var(--line);
            background:#F4FAF6; }
.rv-stage .rv-num { display:CLIENT-CLIENT; min-width:19px; height:19px; line-height:19px;
                    text-align:center; border-radius:6px; background:#15803D; color:#fff;
                    font-size:12px; font-weight:700; }
.rv-tabs { border-bottom:2px solid var(--line); }
.rv-tabs .rv-tab.is-on { color:#14663A; }
.rv-tabs .rv-num { background:#DCFCE7; color:#14663A; }
.rv-tabs .rv-tab.is-on .rv-num { background:#15803D; color:#fff; }
.rv-chip { background:#DCFCE7 !important; color:#14663A !important; border-color:#BFE0CB !important; }
.rv-CLIENT.ok { background:#DCFCE7; border-color:#BFE0CB; color:#14663A; }
.rv-CLIENT.warn { background:#FEF3C7; border-color:#FDE68A; color:#78350F; }

/* Окно просмотра. Обвязка — та, при которой документ виден целиком по ширине. */
@keyframes rv-spin { to { transform: rotate(360deg); } }
.rv-spinner { display:CLIENT-CLIENT; width:26px; height:26px; border-radius:50%;
              border:3px solid #DCEEE2; border-top-color:#15803D; animation:rv-spin .9s linear infinite; }
.rv-loading { display:flex; flex-direction:column; align-items:center; justify-content:center;
              gap:10px; height:100%; min-height:180px; color:#6B7C70; font-size:13px; }
.rv-modal-win { height:100%; min-height:0; }
.rv-modal-body { flex:1 1 auto; min-height:0; overflow:hidden; padding:12px; display:flex; }
.rv-modal-body .zp-preview { flex:1 1 auto; min-width:0; width:100%; }
.rv-modal-body .zp-shell { width:100%; display:flex; flex-direction:column; }
.rv-modal-body .zp-host { width:100% !important; }
.rv-modal-body .zp-canvas { margin:0 auto; }
.rv-modal-body .html-stage { width:794.5px; margin:0 !important; padding:0 !important;
                             border:0 !important; background:#fff !important; }
.rv-modal-body .html-stage > div,
.rv-modal-body .html-stage > section { margin:0; }
/* Входящий файл-картинка: показываем снимок целиком, без полей листа */
.rv-modal-body .html-stage.is-image { display:flex; align-items:center; justify-content:center; }
.rv-modal-body .html-stage.is-image > img { max-width:100%; max-height:100%; width:auto; height:auto;
                                            object-fit:contain; display:CLIENT; margin:auto; }
.rv-modal-body .html-stage.is-image > iframe { flex:1 1 auto; width:100%; height:100%; border:0; background:#fff; }
.rv-modal-note { flex:0 0 auto; }

/* Переменные открытого документа: подсвечены и подняты наверх списка */
.rv-field.is-doc { background:#F1FBF4; border-color:#86EFAC !important; }
.rv-field.is-doc .rv-flabel::after { content:' · этот документ'; color:#15803D; font-weight:600; }

/* Правило переменной: подпись источника и переключатель фильтра */
.rv-rule { display:CLIENT-CLIENT; margin-left:7px; padding:1px 7px; border-radius:999px;
           font-size:10.5px; font-weight:600; vertical-align:middle; }
.rv-rule-client { background:#EAF4EE; color:#14663A; border:1px solid #BFE0CB; }
.rv-rule-doc { background:#EEF2F6; color:#38455C; border:1px solid #D8DEE6; }
.rv-rule-gen { background:#DCFCE7; color:#14663A; border:1px solid #86EFAC; }
.rv-rule-formula { background:#FEF3C7; color:#78350F; border:1px solid #FDE68A; }
.rv-filter { margin-left:auto; display:flex; gap:5px; }
.rv-filter button { padding:4px 10px; border:1px solid var(--line); background:#fff; border-radius:8px;
                    font-family:inherit; font-size:12px; cursor:pointer; color:#38455C; }
.rv-filter button.is-on { background:#15803D; border-color:#15803D; color:#fff; font-weight:600; }
.rv-filter-note { font-size:11.5px; color:#6B7C70; font-weight:500; margin-left:8px; }
.rv-field.is-doc { background:#F1FBF4; border-color:#86EFAC !important; }

/* Внутри окна никаких обводок: объём даёт тень самого окна */
.rv-modal-body .zp-host,
.rv-modal-body .zp-preview,
.rv-modal-body .zp-canvas > * { border:0 !important; outline:0 !important; }

/* Жёлтый маркер подставленных значений прямо в документе: видно, что заполнено машиной */
.rv-modal-body .html-stage [data-var] { background:rgba(254,243,199,.92); border-radius:2px;
                                        box-shadow:0 0 0 1px rgba(234,179,8,.35); }
.rv-modal-body .html-stage [data-var=""] { background:none; box-shadow:none; }

/* Связь переменная ↔ документ. Выбранная переменная остаётся подсвеченной,
   пока работаешь с ней: и в панели, и на своём месте в документе. */
.rv-field.is-active { border-color:#F59E0B !important; background:#FFFCF2 !important;
                      box-shadow:0 0 0 3px rgba(245,158,11,.18); }
.rv-field.is-active .rv-flabel { color:#92400E; }
.rv-field.is-linked .rv-flabel::after { content:' ← в документе'; font-size:10.5px;
                                        font-weight:600; color:#B45309; }
.rv-modal-body .html-stage [data-var].is-picked { background:#FDE68A !important;
      box-shadow:0 0 0 2px #F59E0B, 0 0 12px rgba(245,158,11,.45) !important; border-radius:3px; }
.rv-modal-body .html-stage [data-var] { cursor:pointer; }

/* Колёсико загрузки в плитках: видно, пока миниатюра не отрисована */
.rv-thumb-frame { position:relative; }
.rv-thumb-frame .rv-spinner { position:absolute; top:50%; left:50%; margin:-13px 0 0 -13px;
                              z-CLIENT:3; display:none; }
.rv-thumb-frame:not(.is-ready) .rv-spinner { display:CLIENT-CLIENT; }
.rv-thumb-frame.is-ready .rv-spinner { display:none; }
.rv-thumb-frame:not(.is-ready) { background:#F1F4F7; }

/* Блок №2 тянется вместе с блоком 1 до конца колонки, а не прилипает к экрану */
.rv-panel.rv-right { position:static; top:auto; height:auto; align-self:stretch;
                     min-height:420px; }

/* Пока открыт документ, окно визора занимает экран до самого верха. Панель
   переменных в этот момент тоже поднимается к верху: белого куска шапки справа
   быть не должно, работать нужно с документом и его переменными. */
body.rv-viewing .rv-panel.rv-right { position:fixed; top:0; right:0; height:100vh;
      width:calc(33.333% - 4px); z-CLIENT:65; border-radius:0; margin:0;
      box-shadow:-18px 0 40px rgba(16,24,32,.16); }
body.rv-viewing .rv-panel.rv-right .rv-body { padding-bottom:18px; }

/* Ссылка на папку заявки на Google CLIENT в шапке карточки */
.rv-CLIENT { display:flex; align-items:center; gap:9px; flex-wrap:wrap; margin-top:9px;
            padding:8px 11px; background:#F7FBF8; border:1px solid #E3EFE6; border-radius:10px; }
.rv-CLIENT-k { font-size:12px; font-weight:600; color:#5B6B60; text-transform:uppercase;
              letter-spacing:.03em; }
.rv-CLIENT input { flex:1; min-width:220px; padding:6px 9px; border:1px solid var(--line);
                  border-radius:8px; font-family:inherit; font-size:12.5px; }
.rv-CLIENT-edit { border:0; background:none; color:#15803D; font-family:inherit; font-size:11.5px;
                 cursor:pointer; text-decoration:underline; padding:0; }

/* Индикатор у плитки: рядом с именем файла и весом. Крутится, пока миниатюра
   не легла в кэш браузера; после загрузки становится зелёной галочкой —
   значит документ откроется сразу. */
.rv-tile-dot { display:CLIENT-CLIENT; width:13px; height:13px; border-radius:50%;
               margin-left:7px; vertical-align:-2px; border:2px solid #DCEEE2;
               border-top-color:#15803D; animation:rv-spin .9s linear infinite;
               position:relative; }
.rv-tile-dot.is-cached { border:0; background:#16A34A; animation:none; }
.rv-tile-dot.is-cached::after { content:'✓'; position:absolute; left:2px; top:-2px;
               color:#fff; font-size:10px; font-weight:700; line-height:13px; }
.rv-tile-dot.is-failed { border:0; background:#FCA5A5; animation:none; }
.rv-tile-dot.is-failed::after { content:'!'; position:absolute; left:4.5px; top:-2px;
               color:#fff; font-size:10px; font-weight:700; line-height:13px; }

/* Разделы панели: данные клиента, общее для документов, затем каждый документ.
   Тонкая рамка показывает, какие переменные относятся к какому банку. */
/* Шапка панели: название, счётчик заполнения, кнопка «свернуть блоки» */
.rv-phead { position:sticky; top:0; z-CLIENT:6; background:#fff; border:1px solid #E4EDE7;
            border-radius:14px; box-shadow:0 6px 16px rgba(16,24,32,.07);
            padding:10px 12px 9px; margin-bottom:10px; }
.rv-phead-top { display:flex; align-items:center; gap:8px; }
.rv-phead .rv-stage { font-size:14.5px; font-weight:700; letter-spacing:0; }
.rv-progress { display:flex; align-items:center; gap:8px; margin-top:6px;
               font-size:11.5px; font-weight:600; letter-spacing:0; }
.rv-progress.is-urgent #rv-progress-text { color:#C0342B; }
.rv-progress.is-done #rv-progress-text { color:#15803D; }
.rv-progress.is-done #rv-progress-text::after { content:' ✓'; font-weight:700; }
.rv-collapse-all { margin-left:auto; border:1px solid #DCE7E0; background:#F7FBF8;
                   color:#5C6B62; font-size:10.5px; border-radius:999px; padding:3px 9px;
                   cursor:pointer; }
.rv-collapse-all:hover { background:#EEF6F1; }

/* Раздел: рамка с тенью, тело раскрывается и закрывается нажатием на заголовок */
.rv-blk { border:1px solid #E4EDE7; border-radius:14px; background:#fff;
          margin-bottom:10px; overflow:hidden; box-shadow:0 3px 10px rgba(16,24,32,.05); }
.rv-blk-head { display:flex; align-items:center; gap:8px; width:100%; text-align:left;
               border:0; border-bottom:1px solid #EDF4EF; background:#FBFDFC;
               padding:10px 12px; cursor:pointer;
               box-shadow:0 2px 6px rgba(16,24,32,.05); }
.rv-blk-head:hover { background:#F5FAF7; }
.rv-blk-t { font-size:12.5px; font-weight:700; color:#243027; letter-spacing:0;
            text-transform:none; }
.rv-blk-n { font-size:10.5px; font-weight:700; color:#6B7C70; background:#EFF5F1;
            border-radius:999px; padding:1px 7px; text-transform:none; letter-spacing:0; }
.rv-blk-arrow { margin-left:auto; color:#8C9A91; font-size:11px; transition:transform .15s; }
.rv-sec.is-closed .rv-blk-arrow { transform:rotate(-90deg); }
.rv-blk.is-closed .rv-blk-body { display:none; }
.rv-sec.is-closed .rv-blk-head { border-bottom:0; }
.rv-blk-body { padding:4px 12px 10px; }

/* Поле переменной: название сверху, значение, под ним источник — у всех одинаково */
.rv-fname { font-size:12.5px; font-weight:600; color:#2B3A31; margin-bottom:6px; }
.rv-input { flex:1; min-width:0; font:inherit; font-size:13px; color:#1F2A24;
            border:1px solid #DFE8E3; border-radius:10px; background:#fff;
            padding:7px 9px; line-height:1.4; resize:none; overflow:hidden;
            min-height:34px; }
.rv-input:focus { outline:none; border-color:#9CC7AE; box-shadow:0 0 0 3px #E8F4EC; }
.rv-input.is-empty { border-color:#EBC7C2; }
.rv-fsrc { display:flex; align-items:center; gap:8px; margin-top:6px; font-size:10.5px; }
.rv-fsrc .rv-src { color:#6E7D74; }
.rv-fsrc .rv-docs { color:#9AA69D; margin-left:auto; }
.rv-act-off { color:#C7D3CB; border-color:#EAF1EC; background:#FBFDFC; cursor:default; }
.rv-rule-shared { background:#EEF2F6; color:#38455C; border:1px solid #D8DEE6; }

/* Подпись переменной и её правило: название, бейдж-правило, кнопка кубика */
.rv-flabel { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.rv-frule { font-size:11px; color:#7A8A80; line-height:1.35; margin-top:3px; }

/* Кружочек «i» у переменной: инструкция показывается окном поверх страницы */
/* Справа от поля — две ячейки по высоте: сверху информация, снизу кубик */
.rv-fedit { display:flex; align-items:stretch; gap:6px; }
.rv-fedit .rv-input { flex:1; min-width:0; }
.rv-acts { display:grid; grid-template-rows:1fr 1fr; gap:3px; flex:0 0 auto; width:30px; }
.rv-info, .rv-acts .rv-act { width:100%; height:100%; min-height:16px; border-radius:9px;
           border:1px solid #BFD9C8; background:#EFF7F1; color:#15803D; cursor:pointer;
           font-size:11px; font-weight:700; line-height:1; padding:0;
           display:flex; align-items:center; justify-content:center; }
.rv-info { font-family:Georgia, serif; font-style:italic; }
.rv-info:hover, .rv-acts .rv-act:hover { background:#DFF0E5; }
.rv-instr-back { position:fixed; inset:0; background:rgba(17,24,39,.45); z-CLIENT:88;
                 display:none; align-items:center; justify-content:center; padding:16px; }
.rv-instr-back.is-on { display:flex; }
.rv-instr-win { background:#fff; border-radius:14px; max-width:620px; width:100%;
                max-height:70vh; overflow:auto; box-shadow:0 24px 70px rgba(16,24,32,.35); }
.rv-instr-head { display:flex; align-items:center; gap:10px; padding:12px 14px;
                 border-bottom:1px solid #E9F1EC; font-weight:700; color:#14663A; }
.rv-instr-head button { margin-left:auto; border:0; background:none; font-size:20px; line-height:1;
                        color:#6B7C70; cursor:pointer; }
.rv-instr-body { padding:14px; font-size:13px; line-height:1.55; color:#27303F; white-space:pre-wrap; }
.rv-instr-meta { padding:0 14px 14px; font-size:11.5px; color:#7A8A80; }

/* Кнопки шага: работают сами, значок сообщает, выполнено ли действие */
.rv-auto { display:CLIENT-flex; align-items:center; gap:7px; }
.rv-auto-dot { width:13px; height:13px; border-radius:50%; border:2px solid rgba(255,255,255,.85);
               background:transparent; display:CLIENT-CLIENT; position:relative; flex:0 0 auto; }
.rv-auto[data-done="1"] .rv-auto-dot { border-color:#7BF0A8; background:#22C55E;
               border-width:0; }
.rv-auto[data-done="1"] .rv-auto-dot::after { content:'✓'; position:absolute; inset:0;
               color:#fff; font-size:9px; font-weight:700; line-height:13px; text-align:center; }
.rv-auto.is-busy .rv-auto-dot { border-color:rgba(255,255,255,.9); border-top-color:transparent;
               animation:rv-spin .8s linear infinite; }
@keyframes rv-spin { to { transform:rotate(360deg); } }
.rv-auto-fill { background:#6D4AC4 !important; border-color:#6D4AC4 !important; }
.rv-auto-fill:hover { background:#5E3EB0 !important; }
.rv-auto-fill[data-done="1"] { box-shadow:0 0 0 2px #D9CDF5 inset; }

/* Тип продукта заявки: видно, какой нужен клиенту, и можно поменять */
.rv-prod { display:flex; align-items:center; gap:8px; margin-top:8px; flex-wrap:wrap; }
.rv-prod-k { font-size:10.5px; text-transform:uppercase; letter-spacing:.05em; color:#8C9A91; }
.rv-prod-select { font:inherit; font-size:12.5px; font-weight:600; color:#1F5133;
                  border:1px solid #CBE3D4; background:#F4FBF6; border-radius:9px;
                  padding:5px 8px; max-width:420px; cursor:pointer; }
.rv-prod-select:hover { background:#EAF6EE; }
.rv-prod-note { font-size:11px; color:#7C8A80; }
"""
