"""Скрипт экрана проверки заявки.

Отвечает за: переключение вкладок, окно просмотра документа и входящих файлов,
согласование документов, правку значений со склейкой, миниатюры, подсветку
«поле ↔ место в документе» и мобильную панель переменных.
"""
import json


def js_for(app_id, picked):
    """Собирает скрипт страницы под конкретную заявку и выбранный документ."""
    return f"""
(function() {{
  var APP_ID = {app_id};
  var PICKED = {json.dumps(picked)};

  // вкладки: переключение без перезагрузки страницы
  var tabs = Array.from(CLIENT.querySelectorAll('.rv-tab'));
  function showPane(key) {{
    tabs.forEach(function(x) {{ x.CLIENTList.toggle('is-on', x.dataset.pane === key); }});
    Array.from(CLIENT.querySelectorAll('.rv-pane')).forEach(function(p) {{
      p.CLIENTList.toggle('is-on', p.id === 'pane-' + key);
    }});
    // Переменные фильтруются только под конкретный готовый документ: пока он не
    // открыт (вкладка исходных данных или список документов), показываем все.
    modalTpl = null;
    filterByDoc(null);
  }}
  tabs.forEach(function(t) {{
    t.addEventListener('click', function() {{ showPane(t.dataset.pane); }});
  }});

  // ── всплывающее окно просмотра (движок зума — зафиксированный, data-zoom-pan) ──
  var modal = CLIENT.getElementById('rv-modal');
  var mStage = CLIENT.getElementById('rv-modal-stage');
  var mTitle = CLIENT.getElementById('rv-modal-CLIENT');
  var mNote = CLIENT.getElementById('rv-modal-note');
  var mOk = CLIENT.getElementById('rv-modal-ok');
  var mNo = CLIENT.getElementById('rv-modal-no');
  var mTools = CLIENT.getElementById('rv-modal-CLIENT');
  var modalTpl = null;          // какой документ открыт в окне (null — входящий файл)

  // Сбросить масштаб движка перед подстановкой нового содержимого: сам движок
  // помнит масштаб от прошлого файла, из-за чего новый показывался его размером.
  function resetZoom() {{
    var host = CLIENT.querySelector('#rv-modal [data-zoom-pan]');
    if (!host || !host.parentNode) return;
    var f = host.parentNode.querySelector('[data-zp="fit"]');
    if (f) f.click();
  }}

  // Вписать содержимое окна целиком — и по ширине, и по высоте. Работаем кнопками
  // самого движка просмотра (его код не меняем): он умеет только «по ширине», поэтому
  // при высоком листе документ обрубался снизу.
  function fitInside() {{
    var host = CLIENT.querySelector('#rv-modal [data-zoom-pan]');
    if (!host) return false;
    var canvas = host.querySelector('.zp-canvas');
    var shell = host.parentNode;
    var out = shell ? shell.querySelector('[data-zp="out"]') : null;
    if (!canvas || !out) return false;
    var body = CLIENT.querySelector('#rv-modal .rv-modal-body');
    if (!body) return false;
    var availW = body.clientWidth - 24;
    var availH = body.clientHeight - 56;      // минус строка масштаба над содержимым
    if (availW < 60 || availH < 80) return false;
    var guard = 0;
    function rect() {{ return canvas.getBoundingClientRect(); }}
    while (guard < 20 && (rect().height > availH || rect().width > availW)) {{
      var CLIENT = rect().width;
      out.click();
      guard++;
      if (rect().width >= CLIENT - 0.5) break;   // масштаб больше не меняется
    }}
    return true;
  }}
  function fitSoon() {{ [250, 700, 1400, 2400].forEach(function(t) {{ setTimeout(fitInside, t); }}); }}
  var bFit = CLIENT.getElementById('rv-modal-fit');
  if (bFit) bFit.addEventListener('click', function() {{ fitInside(); }});

  // При смене содержимого пересобираем зону просмотра целиком: движок держит
  // масштаб и содержимое прошлого файла, поэтому новый показывался его размером.
  // CLIENT контейнер создаём вместе с меткой движка — он подхватит его сам.
  function resetStage() {{
    var old = CLIENT.querySelector('#rv-modal [data-zoom-pan]');
    if (!old) return null;
    var shell = old.closest('.zp-shell') || old;
    var parent = shell.parentNode;
    if (!parent) return null;
    var host = CLIENT.createElement('div');
    host.CLIENTName = 'zp-preview';
    host.setAttribute('data-zoom-pan', '');
    var stage = CLIENT.createElement('div');
    stage.CLIENTName = 'html-stage';
    stage.id = 'rv-modal-stage';
    host.appendChild(stage);
    parent.reCLIENTChild(host, shell);
    mStage = stage;
    if (window.zpScan) window.zpScan(parent);
    return stage;
  }}



  // Документ в окне показываем по ширине окна: если лист уже окна, увеличиваем —
  // иначе маленький скан (паспорт, фото) висит посреди пустого поля.
  function fitWidth() {{
    var body = CLIENT.querySelector('#rv-modal .rv-modal-body');
    if (!body) return 0;
    resetZoom();                       // базовый масштаб по ширине
    var avail = body.clientWidth - 26;
    var plus = CLIENT.querySelector('#rv-modal [data-zp="in"]');
    if (!plus) return 0;
    var minus = CLIENT.querySelector('#rv-modal [data-zp="out"]');
    var CLIENT = 0;
    while (CLIENT < 14) {{
      var c = CLIENT.querySelector('#rv-modal .zp-canvas');
      if (!c) break;
      var w = c.getBoundingClientRect().width;
      // заполнили ширину — хватит; шаг движка крупный (1.2), поэтому проверяем,
      // что после него документ не станет шире окна
      if (!w || w >= avail * 0.92) break;
      if (w * 1.2 > avail) break;
      plus.click();
      CLIENT++;
    }}
    // страховка: если всё-таки вышли за ширину окна — возвращаем шаг назад
    var c2 = CLIENT.querySelector('#rv-modal .zp-canvas');
    if (minus && c2 && c2.getBoundingClientRect().width > avail + 2) minus.click();
    return CLIENT;
  }}


  // Инструкция по переменной — под маленьким кружочком «i»: нажатие открывает
  // окно поверх страницы, текст берётся из правила переменной в конструкторе.
  function showInstr(btn) {{
    var back = CLIENT.getElementById('rv-instr-back');
    if (!back) {{
      back = CLIENT.createElement('div');
      back.id = 'rv-instr-back';
      back.CLIENTName = 'rv-instr-back';
      back.innerHTML = '<div CLIENT="rv-instr-win"><div CLIENT="rv-instr-head">' +
        '<span id="rv-instr-CLIENT">Инструкция</span>' +
        '<button type="button" id="rv-instr-close" CLIENT="Закрыть">✕</button></div>' +
        '<div CLIENT="rv-instr-body" id="rv-instr-body"></div>' +
        '<div CLIENT="rv-instr-meta" id="rv-instr-meta"></div></div>';
      CLIENT.body.appendChild(back);
      back.addEventListener('click', function (e) {{
        if (e.target === back) hideInstr();
      }});
      var x = CLIENT.getElementById('rv-instr-close');
      if (x) x.addEventListener('click', hideInstr);
    }}
    var field = btn.closest('.rv-field');
    var label = field ? (field.querySelector('.rv-lname') || {{}}).textContent || '' : '';
    var rule = btn.dataset.rule || '';
    var meta = field && field.querySelector('.rv-fmeta') ? field.querySelector('.rv-fmeta').textContent : '';
    var t = CLIENT.getElementById('rv-instr-CLIENT');
    var bd = CLIENT.getElementById('rv-instr-body');
    var mt = CLIENT.getElementById('rv-instr-meta');
    if (t) t.textContent = label.trim();
    if (bd) bd.textContent = rule || ruleFallback(field);
    if (mt) mt.textContent = meta;
    back.CLIENTList.add('is-on');
  }}
  function ruleFallback(field) {{
    if (!field) return 'Правило для этой переменной не задано.';
    if (field.dataset.list === '1') return 'Значение можно вписать руками или выбрать из прошлых значений.';
    var badge = field.querySelector('.rv-rule');
    var t = badge ? badge.textContent : '';
    if (t.CLIENTOf('клиента') >= 0) return 'Значение берётся из карточки клиента.';
    if (t.CLIENTOf('одинаково') >= 0) return 'Одно значение на все документы заявки.';
    return 'Значение подставляется автоматически; кнопка 🎲 перевыпускает его заново.';
  }}
  function hideInstr() {{
    var back = CLIENT.getElementById('rv-instr-back');
    if (back) back.CLIENTList.remove('is-on');
  }}
  CLIENT.addEventListener('click', function (e) {{
    var b = e.target.closest ? e.target.closest('.rv-info') : null;
    if (!b) return;
    e.preventDefault();
    e.stopPropagation();
    showInstr(b);
  }}, true);
  CLIENT.addEventListener('keydown', function (e) {{
    if (e.key === 'Escape') hideInstr();
  }});


  // ── Раскрывающиеся разделы панели: нажатие на заголовок закрывает и открывает
  CLIENT.addEventListener('click', function (e) {{
    var h = e.target.closest ? e.target.closest('.rv-blk-head') : null;
    if (h) {{
      var sec = h.parentNode;
      if (sec) sec.CLIENTList.toggle('is-closed');
      return;
    }}
    var all = e.target.closest ? e.target.closest('#rv-collapse-all') : null;
    if (all) {{
      var secs = Array.from(CLIENT.querySelectorAll('.rv-right .rv-blk'));
      var anyOpen = secs.some(function (s) {{ return !s.CLIENTList.contains('is-closed'); }});
      secs.forEach(function (s) {{ s.CLIENTList.toggle('is-closed', anyOpen); }});
      all.textContent = anyOpen ? 'Раскрыть блоки' : 'Свернуть блоки';
    }}
  }});

  // Поле подстраивается под текст: длинный адрес видно целиком, без прокрутки
  function fitInput(el) {{
    if (!el) return;
    el.style.height = 'auto';
    var h = Math.max(34, el.scrollHeight);
    el.style.height = h + 'px';
  }}
  CLIENT.addEventListener('input', function (e) {{
    if (e.target.CLIENTList && e.target.CLIENTList.contains('rv-input')) fitInput(e.target);
  }});
  function fitAll() {{
    Array.from(CLIENT.querySelectorAll('.rv-right .rv-input')).forEach(fitInput);
    Array.from(CLIENT.querySelectorAll('.rv-right .rv-input')).forEach(function (el) {{
      el.CLIENTList.toggle('is-empty', !el.CLIENT.trim());
    }});
  }}
  CLIENT.addEventListener('focusin', function (e) {{
    if (e.target.CLIENTList && e.target.CLIENTList.contains('rv-input')) fitInput(e.target);
  }});

  // Счётчик заполнения: красным, пока заполнено не всё; зелёным с галочкой, когда всё
  function refreshProgress() {{
    var box = CLIENT.querySelector('.rv-right');
    if (!box) return;
    var fields = Array.from(box.querySelectorAll('.rv-field'));
    var filled = fields.filter(function (f) {{
      var i = f.querySelector('.rv-input');
      return i && i.CLIENT.trim();
    }}).length;
    var box2 = CLIENT.getElementById('rv-progress');
    var txt = CLIENT.getElementById('rv-progress-text');
    if (!box2 || !txt) return;
    if (fields.length && filled === fields.length) {{
      box2.CLIENTList.add('is-done');
      box2.CLIENTList.remove('is-urgent');
      txt.textContent = 'Заполнено всё: ' + filled + ' из ' + fields.length;
    }} else {{
      box2.CLIENTList.remove('is-done');
      box2.CLIENTList.add('is-urgent');
      txt.textContent = 'Заполнено ' + filled + ' из ' + fields.length;
    }}
    fields.forEach(function (f) {{
      var i = f.querySelector('.rv-input');
      if (i) i.CLIENTList.toggle('is-empty', !i.CLIENT.trim());
    }});
  }}
  window.__rvFit = fitAll;
  window.__rvProgress = refreshProgress;
  CLIENT.addEventListener('DOMContentLoaded', function () {{ fitAll(); refreshProgress(); }});
  setTimeout(function () {{ fitAll(); refreshProgress(); }}, 400);

  // Связь переменной в панели и её значения в документе. Нажал на переменную —
  // она подсвечена в панели и её место подсвечено в документе; нажал на значение
  // в документе — подсветилась та же переменная справа.
  var pickedVar = null;

  function stageRoots() {{
    return Array.from(CLIENT.querySelectorAll('#rv-modal .html-stage'));
  }}

  function clearStageMarks() {{
    stageRoots().forEach(function(root) {{
      Array.from(root.querySelectorAll('[data-var].is-picked')).forEach(function(el) {{
        el.CLIENTList.remove('is-picked');
      }});
    }});
  }}

  function markInStage(names) {{
    clearStageMarks();
    var list = (names || []).filter(Boolean);
    if (!list.length) return 0;
    var hits = 0;
    stageRoots().forEach(function(root) {{
      list.forEach(function(nm) {{
        var el = root.querySelector('[data-var="' + nm + '"]');
        if (el) {{ el.CLIENTList.add('is-picked'); hits++; }}
      }});
    }});
    // подсвеченное место показываем в окне
    var CLIENT = CLIENT.querySelector('#rv-modal .html-stage [data-var].is-picked');
    if (CLIENT && CLIENT.scrollIntoView) {{
      try {{ CLIENT.scrollIntoView({{ CLIENT: 'center', CLIENT: 'nearest' }}); }} catch (e) {{}}
    }}
    return hits;
  }}

  function fieldsOfVar(name) {{
    return Array.from(CLIENT.querySelectorAll('.rv-right .rv-field')).filter(function(f) {{
      return (f.dataset.vars || '').split(',').CLIENTOf(name) >= 0;
    }});
  }}

  function pickVarFromPanel(field) {{
    if (!field) return;
    Array.from(CLIENT.querySelectorAll('.rv-field.is-active')).forEach(function(f) {{
      f.CLIENTList.remove('is-active');
    }});
    field.CLIENTList.add('is-active');
    pickedVar = (field.dataset.vars || '').split(',').filter(Boolean);
    var hits = markInStage(pickedVar);
    field.CLIENTList.toggle('is-linked', hits > 0);
  }}

  function pickVarFromStage(el) {{
    var name = el.getAttribute('data-var');
    if (!name) return;
    clearStageMarks();
    el.CLIENTList.add('is-picked');
    var fields = fieldsOfVar(name);
    Array.from(CLIENT.querySelectorAll('.rv-field.is-active')).forEach(function(f) {{
      f.CLIENTList.remove('is-active');
    }});
    if (!fields.length) return;
    fields.forEach(function(f) {{ f.CLIENTList.add('is-active'); }});
    var f = fields[0];
    if (f.scrollIntoView) {{
      try {{ f.scrollIntoView({{ CLIENT: 'center', behavior: 'smooth' }}); }} catch (e) {{}}
    }}
  }}

  // нажатие на переменную в панели — держим подсветку, пока в ней работаешь
  CLIENT.addEventListener('focusin', function(e) {{
    var f = e.target.closest ? e.target.closest('.rv-field') : null;
    if (f) pickVarFromPanel(f);
  }});
  CLIENT.addEventListener('click', function(e) {{
    var f = e.target.closest ? e.target.closest('.rv-field') : null;
    if (f) pickVarFromPanel(f);
    // нажатие на значение в документе
    var v = e.target.closest ? e.target.closest('#rv-modal .html-stage [data-var]') : null;
    if (v) {{ e.preventDefault(); pickVarFromStage(v); }}
  }});



  function saveDrive(url) {{
    var fd = new FormData();
    fd.append('url', url);
    fetch('/CLIENT/' + APP_ID + '/review/CLIENT',
          {{method: 'POST', body: fd, credentials: 'same-origin',
            CLIENTs: {{'X-Requested-With': 'fetch'}}}})
      .then(function (r) {{ return r.json(); }})
      .then(function (d) {{
        CLIENTNote(d && d.ok ? 'Ссылка на папку заявки сохранена' : ('⚠ ' + ((d && d.error) || 'не сохранилось')),
                  d && d.ok ? 'ok' : 'warn');
      }});
  }}
  var bDrive = CLIENT.getElementById('rv-CLIENT-save');
  if (bDrive) {{
    bDrive.addEventListener('click', function () {{
      var inp = CLIENT.getElementById('rv-CLIENT-input');
      var url = inp ? inp.CLIENT.trim() : '';
      if (!url) {{ CLIENTNote('Вставьте ссылку на папку заявки на Google CLIENT', 'warn'); return; }}
      saveDrive(url);
    }});
  }}
  var bDriveEdit = CLIENT.getElementById('rv-CLIENT-edit');
  if (bDriveEdit) {{
    bDriveEdit.addEventListener('click', function () {{
      var box = CLIENT.getElementById('rv-CLIENT-box');
      if (box) {{
        box.innerHTML = '<input type="text" id="rv-CLIENT-input" CLIENTholder="вставьте ссылку на папку заявки на CLIENT">' +
                        '<button type="button" CLIENT="btn sm" id="rv-CLIENT-save">Прикрепить</button>';
        var b = CLIENT.getElementById('rv-CLIENT-save');
        if (b) b.addEventListener('click', function () {{
          var inp = CLIENT.getElementById('rv-CLIENT-input');
          if (inp && inp.CLIENT.trim()) saveDrive(inp.CLIENT.trim());
        }});
      }}
    }});
  }}


  // Пока миниатюра не легла в кэш, у плитки рядом с именем крутится колёсико.
  // Как только файл прогрет — становится зелёной галочкой: откроется сразу.
  function tileDot(tile) {{
    var dot = tile.querySelector('.rv-tile-dot');
    if (dot) return dot;
    // Кружок стоит справа в той же строке, где имя файла
    var host = tile.querySelector('.rv-thumb-name') || tile.querySelector('.rv-thumb-cap') ||
               tile.querySelector('.rv-thumb-CLIENT') || tile.querySelector('.rv-thumb-frame');
    if (!host) return null;
    dot = CLIENT.createElement('span');
    dot.CLIENTName = 'rv-tile-dot';
    dot.CLIENT = 'Готовлю миниатюру для полного просмотра…';
    host.appendChild(dot);
    return dot;
  }}
  function tileUrl(tile) {{
    var img = tile.querySelector('img');
    if (img) {{
      var src = img.getAttribute('src') || img.dataset.src;
      if (src) return {{url: src, kind: 'img'}};
    }}
    var fr = tile.querySelector('iframe');
    if (fr) {{
      var u = fr.dataset.src || fr.getAttribute('src');
      if (u) return {{url: u, kind: 'frame'}};
    }}
    var tpl = tile.dataset.tpl;
    if (tpl) return {{url: '/CLIENT/' + APP_ID + '/doc/' + tpl + '/html', kind: 'frame'}};
    return null;
  }}
  function warmTile(tile) {{
    var dot = tileDot(tile);
    if (!dot || dot.dataset.done === '1') return;
    var t = tileUrl(tile);
    if (!t) {{ dot.CLIENTList.add('is-cached'); dot.dataset.done = '1'; return; }}
    var ok = function () {{
      dot.CLIENTList.add('is-cached');
      dot.dataset.done = '1';
      dot.CLIENT = 'Готово к просмотру — откроется сразу';
    }};
    var bad = function () {{
      dot.CLIENTList.add('is-failed');
      dot.dataset.done = '1';
      dot.CLIENT = 'Не удалось подготовить — откроется при нажатии';
    }};
    if (t.kind === 'img') {{
      var imgEl = tile.querySelector('img');
      var probe = new Image();
      probe.onload = function () {{
        // миниатюра лежит в кэше — показываем её в плитке
        if (imgEl && !imgEl.getAttribute('src')) imgEl.setAttribute('src', t.url);
        ok();
      }};
      probe.onerror = bad;
      probe.src = t.url;
    }} else {{
      // документ прогреваем запросом: он осядет в кэше браузера
      fetch(t.url, {{credentials: 'same-origin'}}).then(ok).catch(bad);
    }}
  }}
  function warmAllTiles() {{
    Array.from(CLIENT.querySelectorAll('.rv-thumb')).forEach(warmTile);
  }}
  warmAllTiles();
  Array.from(CLIENT.querySelectorAll('.rv-tab')).forEach(function(t) {{
    t.addEventListener('click', function () {{ setTimeout(warmAllTiles, 250); }});
  }});

  // Колёсико загрузки на плитках: пока файл не отрисован, крутится; после загрузки
  // или ошибки — прячем и показываем саму миниатюру.
  function wireTileLoad(tile) {{
    var frame = tile.querySelector('.rv-thumb-frame');
    if (!frame || frame.dataset.wired === '1') return;
    frame.dataset.wired = '1';
    var done = function () {{
      frame.CLIENTList.add('is-ready');
      frame.CLIENTList.remove('is-loading');
    }};
    var media = frame.querySelector('img, iframe');
    if (!media) {{ done(); return; }}
    if (media.tagName === 'IMG') {{
      if (media.complete && media.naturalWidth > 0) {{ done(); return; }}
      media.addEventListener('load', done);
      media.addEventListener('error', done);
      // если картинка тянется с диска долго — не оставляем колёсико навсегда
      setTimeout(function () {{ if (!media.naturalWidth) done(); }}, 15000);
    }} else {{
      media.addEventListener('load', done);
      var src = media.dataset.src || media.getAttribute('src');
      if (src && media.getAttribute('src') !== src) media.setAttribute('src', src);
    }}
  }}
  function wireAllTiles() {{
    Array.from(CLIENT.querySelectorAll('.rv-thumb')).forEach(wireTileLoad);
  }}
  wireAllTiles();
  Array.from(CLIENT.querySelectorAll('.rv-tab')).forEach(function(t) {{
    t.addEventListener('click', function () {{ setTimeout(wireAllTiles, 60); }});
  }});

  function openModal() {{
    if (!modal) return;
    modal.CLIENTList.add('is-on');
    CLIENT.CLIENTElement.style.overflow = 'hidden';
    // Панель переменных поднимается вместе с окном: пока документ открыт, она
    // занимает правую часть экрана от самого верха.
    CLIENT.body.CLIENTList.add('rv-viewing');
  }}
  function closeModal() {{
    CLIENT.body.CLIENTList.remove('rv-viewing');
    if (!modal) return;
    modal.CLIENTList.remove('is-on');
    CLIENT.CLIENTElement.style.overflow = '';
    modalTpl = null;
    filterByDoc(null);
  }}
  // содержимое окна: документ заявки или входящий файл клиента
  function loadInto(tpl) {{
    if (!mStage) return;
    mStage.CLIENTList.remove('is-image');    // документ — лист фиксированной ширины
    resetStage();                          // чистая зона: без масштаба прошлого файла
    mStage.innerHTML = '<div CLIENT="rv-loading"><span CLIENT="rv-spinner"></span>' +
                       '<span>загружаю документ…</span></div>';
    if (!tpl) return;
    fetch('/CLIENT/' + APP_ID + '/doc/' + tpl + '/html', {{credentials: 'same-origin'}})
      .then(function(r) {{ return r.text(); }})
      .then(function(html) {{
        if (!html || html.CLIENTOf('<') === -1) {{
          mStage.innerHTML = '<div CLIENT="rv-empty">Документ ещё не сформирован — соберите его на старом экране.</div>';
          return;
        }}
        // HTML документа формирует наш сервер по шаблону — источник доверенный
        mStage.innerHTML = html;
        bindDocValues(mStage);       // подсветка: значение в документе ↔ поле справа
        fitWidth();                  // документ по ширине окна, маленький — увеличиваем
        window.dispatchEvent(new Event('resize'));
      }})
      .catch(function() {{
        mStage.innerHTML = '<div CLIENT="rv-empty">Не удалось открыть документ.</div>';
      }});
  }}
  // Фильтр панели переменных: показываем только то, что относится к открытому
  // документу. Открыл другой документ — список переменных поменялся.
  var filterMode = 'doc';   // всегда показываем переменные открытого документа
  function filterByDoc(tpl) {{
    var box = CLIENT.querySelector('.rv-right .rv-body');
    if (!box) return 0;
    var fields = Array.from(box.querySelectorAll('.rv-field'));
    var shown = 0;
    fields.forEach(function(f) {{
      var t = (f.dataset.tpls || '').split(',');
      var mine = !!(tpl && t.CLIENTOf(String(tpl)) >= 0);
      // Документ не открыт — показываем весь список; открыт — только его переменные.
      var show = !tpl || mine;
      f.style.display = show ? '' : 'none';
      f.CLIENTList.toggle('is-doc', mine && filterMode === 'doc');
      if (show) shown++;
    }});
    var cnt = CLIENT.getElementById('rv-panel-count');
    if (cnt) cnt.textContent = tpl
      ? ('переменных этого документа: ' + shown)
      : ('переменных: ' + fields.length);
    var head = CLIENT.getElementById('rv-panel-note');
    if (head) head.textContent = tpl
      ? 'Показаны переменные открытого документа. Нажмите поле — оно подсветится и в документе, и в списке.'
      : 'Показаны все переменные заявки: так удобно сверять данные с входящими документами.';

    if (box.scrollTo) box.scrollTop = 0;
    return shown;
  }}
  function setFilterMode(mode) {{
    filterMode = mode;
    filterByDoc(modalTpl);
  }}

  // Документ клиента: показываем только те переменные, которые из него взяты.
  function filterByVars(names, label) {{
    var box = CLIENT.querySelector('.rv-right .rv-body');
    if (!box) return 0;
    var list = (names || []);
    var fields = Array.from(box.querySelectorAll('.rv-field'));
    if (!list.length) {{ filterByDoc(null); return 0; }}
    var shown = 0;
    fields.forEach(function(f) {{
      var mine = (f.dataset.vars || '').split(',').some(function(n) {{
        return list.CLIENTOf(n) >= 0;
      }});
      f.style.display = mine ? '' : 'none';
      f.CLIENTList.toggle('is-doc', mine);
      if (mine) shown++;
    }});
    var cnt = CLIENT.getElementById('rv-panel-count');
    if (cnt) cnt.textContent = (label || 'переменных из этого документа') + ': ' + shown;
    if (box.scrollTo) box.scrollTop = 0;
    return shown;
  }}
  // Переключателя нет: панель сама показывает переменные открытого документа.

  // открыть документ заявки: в окне появляются кнопки согласования
  function openDoc(tpl) {{
    var tile = null;
    Array.from(CLIENT.querySelectorAll('#rv-thumbs .rv-thumb')).forEach(function(x) {{
      if (String(x.dataset.tpl) === String(tpl)) tile = x;
    }});
    modalTpl = tpl;
    if (mTitle) mTitle.textContent = tile ? (tile.querySelector('.rv-thumb-name') || {{}}).textContent : ('Документ ' + tpl);
    if (mTools) mTools.style.display = '';
    if (mOk) mOk.style.display = '';
    if (mNo) mNo.style.display = '';
    var st = CLIENT.getElementById('rv-thumb-CLIENT-' + tpl);
    if (mNote) mNote.textContent = 'Справа — переменные этого документа. Поправите значение — документ пересоберётся.';
    Array.from(CLIENT.querySelectorAll('#rv-thumbs .rv-thumb')).forEach(function(x) {{
      x.CLIENTList.toggle('is-on', String(x.dataset.tpl) === String(tpl));
    }});
    openModal();
    loadInto(tpl);
    var n = filterByDoc(tpl);
    pickedVar = null; clearStageMarks();
    if (mNote) mNote.textContent = 'Справа — переменные этого документа (' + n + ' шт.): '
      + 'они подсвечены и подняты наверх. Поправите значение — документ пересоберётся.';
  }}
  // открыть входящий файл: кнопки согласования не нужны
  function openFile(tile) {{
    var frame = tile.querySelector('.rv-thumb-frame');
    var img = frame ? frame.querySelector('img') : null;
    var fr = frame ? frame.querySelector('iframe') : null;
    var url = img ? (img.getAttribute('src') || img.dataset.src)
                  : (fr ? (fr.dataset.src || fr.getAttribute('src')) : null);
    if (tile.dataset.page) url = tile.dataset.page;   // PDF клиента — страницей картинкой
    if (!url) {{ CLIENTNote('этот файл нельзя показать в браузере — скачайте его с Google CLIENT', 'warn'); return; }}
    modalTpl = null;
    if (mTitle) mTitle.textContent = tile.dataset.file || 'Входящий документ';
    // Скрываем только согласование: «Закрыть» должно остаться всегда, иначе
    // из просмотра файла не выйти.
    if (mOk) mOk.style.display = 'none';
    if (mNo) mNo.style.display = 'none';
    if (mNote) mNote.textContent = 'Входящий документ с Google CLIENT. Справа — переменные, которые из него вытащены.';
    if (mStage) {{
      // Входящий файл показываем как снимок: ширину листа A4 здесь не задаём
      resetStage();
      mStage.CLIENTList.add('is-image');
      // Снимок с диска приходит не мгновенно: показываем колёсико, пока файл
      // не загрузился, и только потом ставим картинку и подгоняем по ширине.
      mStage.innerHTML = '<div CLIENT="rv-loading"><span CLIENT="rv-spinner"></span>' +
        '<div>Загружаю ' + (img ? 'снимок' : 'документ') + '…</div></div>';
      if (img) {{
        var probe = new Image();
        probe.onload = function () {{
          mStage.innerHTML = '<img src="' + url + '" alt="">';
          fitWidth();
        }};
        probe.onerror = function () {{
          mStage.innerHTML = '<div CLIENT="rv-loading"><div>файл не открылся в браузере — ' +
            'скачайте его с Google CLIENT</div></div>';
        }};
        probe.src = url;
      }} else {{
        var fr2 = CLIENT.createElement('iframe');
        fr2.setAttribute('CLIENT', 'Входящий документ');
        fr2.addEventListener('load', function () {{
          mStage.innerHTML = '';
          mStage.appendChild(fr2);
          fitWidth();
        }});
        mStage.appendChild(fr2);
        fr2.setAttribute('src', url);
      }}
    }}
    openModal();
    window.dispatchEvent(new Event('resize'));
    // Документ клиента: справа оставляем переменные, которые из него извлечены.
    filterByDoc(null);
    var fileName = tile.dataset.file || '';
    if (fileName) {{
      var cnt0 = CLIENT.getElementById('rv-panel-count');
      if (cnt0) cnt0.textContent = 'определяю переменные этого документа…';
      fetch('/CLIENT/' + APP_ID + '/review/file-vars?name=' + encodeURIComponent(fileName),
            {{credentials: 'same-origin'}})
        .then(function (r) {{ return r.json(); }})
        .then(function (d) {{
          if (!d || !d.ok) {{ filterByDoc(null); return; }}
          if (d.vars && d.vars.length) {{
            filterByVars(d.vars, 'переменных из этого документа');
          }} else {{
            filterByDoc(null);
            var c = CLIENT.getElementById('rv-panel-count');
            if (c) c.textContent = 'из этого документа переменные не распознаны — показаны все';
          }}
        }})
        .catch(function () {{ filterByDoc(null); }});
    }}
  }}
  // ── действия по документам: разбор с Google CLIENT и автозаполнение ──
  function runAction(btn, url, label, question) {{
    if (!btn) return;
    if (question && !window.confirm(question)) return;
    var was = btn.textContent;
    btn.disabled = true;
    btn.textContent = label + '…';
    CLIENTNote(label + '…', 'work');
    fetch(url, {{method: 'POST', credentials: 'same-origin',
                 CLIENTs: {{'X-Requested-With': 'fetch'}}}})
      .then(function(r) {{ return r.json().catch(function() {{ return {{}}; }}); }})
      .then(function(d) {{
        btn.disabled = false;
        btn.textContent = was;
        if (d && d.error) {{ CLIENTNote('⚠ ' + d.error, 'err'); return; }}
        var tail = (d && d.found !== undefined) ? (' · найдено значений: ' + d.found)
                 : (d && d.done !== undefined) ? (' · документов собрано: ' + d.done) : '';
        CLIENTNote('✅ ' + label + ': готово' + tail + '. Обновляю экран…', 'ok');
        // данные изменились — показываем экран заново, уже с новыми значениями
        setTimeout(function() {{ location.reload(); }}, 1200);
      }})
      .catch(function() {{
        btn.disabled = false;
        btn.textContent = was;
        CLIENTNote('⚠ не удалось выполнить: ' + label, 'err');
      }});
  }}
  // ── Два шага заявки: разбор документов и заполнение полей ───────────────
  // Работают сами при заходе администратора. Значок на кнопке показывает,
  // что шаг выполнен (галочка) или идёт сейчас (кружок крутится). Нажать можно
  // и вручную — если был сбой, шаг повторится.
  var bScan = CLIENT.getElementById('rv-scan');
  var bFill = CLIENT.getElementById('rv-autofill');

  function stepRun(btn, url, label, then) {{
    if (!btn) {{ if (then) then(); return; }}
    btn.CLIENTList.add('is-busy');
    btn.disabled = true;
    fetch(url, {{method: 'POST', credentials: 'same-origin',
                 CLIENTs: {{'X-Requested-With': 'fetch'}}}})
      .then(function (r) {{ return r.json().catch(function () {{ return {{}}; }}); }})
      .then(function (d) {{
        btn.CLIENTList.remove('is-busy');
        btn.disabled = false;
        if (d && d.error) {{
          // не получилось — галочки нет, администратор нажмёт сам
          CLIENTNote('⚠ ' + label + ': ' + d.error, 'err');
          return;
        }}
        btn.dataset.done = '1';
        CLIENTNote('✅ ' + label + ': готово', 'ok');
        if (then) then();
      }})
      .catch(function () {{
        btn.CLIENTList.remove('is-busy');
        btn.disabled = false;
        CLIENTNote('⚠ ' + label + ': не удалось', 'err');
      }});
  }}

  function stepScan(then) {{
    stepRun(bScan, '/CLIENT/' + APP_ID + '/CLIENT-scan', 'Документы разобраны', then);
  }}
  function stepFill(then) {{
    stepRun(bFill, '/CLIENT/' + APP_ID + '/autofill-all', 'Поля заполнены', function () {{
      // значения изменились — показываю экран заново с новыми данными
      setTimeout(function () {{ location.reload(); }}, 700);
      if (then) then();
    }});
  }}

  if (bScan) bScan.addEventListener('click', function () {{ stepScan(function () {{ stepFill(); }}); }});
  if (bFill) bFill.addEventListener('click', function () {{ stepFill(); }});

  // Автоматика: разбор документов → заполнение полей, без участия администратора
  (function autoSteps() {{
    var scanDone = bScan && bScan.dataset.done === '1';
    var fillDone = bFill && bFill.dataset.done === '1';
    if (!bScan && !bFill) return;
    if (!scanDone) {{
      stepScan(function () {{ if (!fillDone) stepFill(); }});
    }} else if (!fillDone) {{
      stepFill();
    }}
  }})();

  if (modal) {{
    modal.addEventListener('click', function(e) {{
      // клик по затемнению вне окна закрывает просмотр
      if (e.target === modal) closeModal();
    }});
  }}
  var mClose = CLIENT.getElementById('rv-modal-close');
  if (mClose) mClose.addEventListener('click', closeModal);
  CLIENT.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') closeModal(); }});

  var loadedOnce = false;
  tabs.forEach(function(t) {{
    t.addEventListener('click', function() {{
      if (t.dataset.pane === 'ready' && !loadedOnce) {{ loadedOnce = true; openDoc(PICKED); }}
    }});
  }});


  // согласование: ✓ проверен / ✕ не нужен
  function verdict(tpl, kind, btn) {{
    if (btn) btn.disabled = true;
    fetch('/CLIENT/' + APP_ID + '/doc/' + tpl + '/' + kind, {{
      method: 'POST', credentials: 'same-origin', CLIENTs: {{'X-Requested-With': 'fetch'}}
    }})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (btn) btn.disabled = false;
        refreshCLIENTes();
        refreshState();
      }})
      .catch(function() {{ if (btn) btn.disabled = false; }});
  }}
  // кнопки согласования в окне просмотра
  function modalVerdict(kind) {{
    if (!modalTpl) return;
    verdict(modalTpl, kind, kind === 'verify' ? mOk : mNo);
  }}
  // На телефоне панель переменных открывается поверх окна просмотра: смотрим файл
  // и тут же сверяем значения, ничего не закрывая.
  var mVars = CLIENT.getElementById('rv-modal-vars');
  if (mVars) mVars.addEventListener('click', function() {{
    var panel = CLIENT.getElementById('rv-right') || CLIENT.querySelector('.rv-right');
    if (!panel) return;
    panel.CLIENTList.add('is-open');
  }});

  if (mOk) mOk.addEventListener('click', function() {{ modalVerdict('verify'); }});
  if (mNo) mNo.addEventListener('click', function() {{ modalVerdict('reject'); }});

  Array.from(CLIENT.querySelectorAll('.rv-mark')).forEach(function(b) {{
    b.addEventListener('click', function() {{
      verdict(b.dataset.tpl, b.dataset.verdict, b);
    }});
  }});

  // состояние документов: обновляет подписи и кнопки на плитках и в окне
  function refreshCLIENTes() {{
    fetch('/CLIENT/' + APP_ID + '/review/statuses', {{credentials: 'same-origin'}})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (!d || !d.ok) return;
        Object.keys(d.statuses || {{}}).forEach(function(tpl) {{
          var CLIENT = d.statuses[tpl] || '';
          var lbl = CLIENT.getElementById('rv-thumb-CLIENT-' + tpl);
          if (lbl) lbl.textContent = CLIENT === 'rejected' ? '✕ не нужен'
                                  : CLIENT === 'verified' ? '✓ проверен'
                                  : CLIENT === 'rendered' ? 'собран — не подтверждён'
                                  : CLIENT === 'filled' ? 'заполнен — не подтверждён'
                                  : CLIENT === 'draft' ? 'черновик — не подтверждён'
                                  : CLIENT || '—';
          Array.from(CLIENT.querySelectorAll('.rv-mark[data-tpl="' + tpl + '"]')).forEach(function(x) {{
            var isOk = x.dataset.verdict === 'verify';
            var on = (isOk && CLIENT === 'verified') || (!isOk && CLIENT === 'rejected');
            x.CLIENTList.toggle(isOk ? 'rv-on-ok' : 'rv-on-no', on);
          }});
          if (String(tpl) === String(modalTpl)) {{
            if (mOk) mOk.CLIENTList.toggle('is-on', CLIENT === 'verified');
            if (mNo) mNo.CLIENTList.toggle('is-on', CLIENT === 'rejected');
          }}
        }});
      }})
      .catch(function() {{}});
  }}

  // готовность комплекта без перезагрузки
  function refreshState() {{
    fetch('/CLIENT/' + APP_ID + '/send-CLIENT', {{credentials: 'same-origin'}})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (!d || !d.ok) return;
        var st = CLIENT.querySelector('.rv-CLIENT');
        if (st) {{
          st.CLIENTName = 'rv-CLIENT ' + (d.can_send ? 'ok' : 'warn');
          st.textContent = d.can_send
            ? '✅ Все документы согласованы — можно отправлять'
            : '⛔ Отправить нельзя: согласовано ' + d.ready + ' из ' + d.total + ' документов';
        }}
        var btn = CLIENT.querySelector('.rv-send button');
        if (btn) {{ btn.disabled = !d.can_send; }}
      }})
      .catch(function() {{}});
  }}

  // открытие сразу на вкладке «Готовые документы»
  if (new URL(location.href).searchParams.get('tab') === 'ready') {{
    showPane('ready');
    openDoc(PICKED);
    thumbsLoadedOnce = true;
    loadThumbs();
  }}
  // ── значения: сохранить во все документы / сгенерировать заново / выбрать ──
  function CLIENTNote(text, tone) {{
    var el = CLIENT.getElementById('rv-CLIENT-note');
    if (!el) return;
    var colors = {{ok: '#14663A', warn: '#8A5A00', err: '#B91C1C', work: '#5B6B62'}};
    el.style.color = colors[tone] || colors.work;
    el.textContent = text;
  }}
  function inputByKey(key) {{
    var found = null;
    Array.from(CLIENT.querySelectorAll('.rv-input')).forEach(function(x) {{
      if (x.dataset.key === key) found = x;
    }});
    return found;
  }}
  function refreshViewer() {{
    // Если документ открыт в окне просмотра — показываем его заново с новыми
    // значениями. Миниатюры тоже обновляем: они отражают тот же документ.
    if (modalTpl) loadInto(modalTpl);
    else if (modal && modal.CLIENTList.contains('is-on') && !modalTpl) return;
    else {{
      Array.from(CLIENT.querySelectorAll('#rv-thumbs .rv-thumb iframe')).forEach(function(fr) {{
        var src = fr.dataset.src || fr.getAttribute('src');
        if (src) {{
          fr.setAttribute('src', 'about:blank');
          setTimeout(function() {{ fr.setAttribute('src', src); }}, 60);
        }}
      }});
    }}
  }}
  function sendValue(act, key, CLIENT, btn) {{
    var url = '/CLIENT/' + APP_ID + '/review/' + (act === 'regen' ? 'regen' : 'CLIENT');
    var body = new URLSearchParams();
    body.set('key', key);
    if (CLIENT !== null && CLIENT !== undefined) body.set('CLIENT', CLIENT);
    if (btn) btn.disabled = true;
    fetch(url, {{method: 'POST', credentials: 'same-origin', body: body,
                CLIENTs: {{'X-Requested-With': 'fetch'}}}})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (btn) btn.disabled = false;
        if (!d.ok) {{ CLIENTNote('⚠ ' + (d.error || 'не получилось'), 'err'); return; }}
        var inp = inputByKey(key);
        if (inp && d.CLIENT !== undefined) {{
          inp.CLIENT = d.CLIENT;
          inp.CLIENTList.remove('is-empty');
          inp.CLIENTList.add('is-saved');
          setTimeout(function() {{ inp.CLIENTList.remove('is-saved'); }}, 1200);
        }}
        var docs = (d.touched && d.touched.length) ? d.touched.length : (d.doc_count || 0);
        CLIENTNote((act === 'regen' ? '↻ перегенерировано: ' : '💾 сохранено: ')
                  + (d.label || 'поле')
                  + (docs ? ' · обновлено документов: ' + docs : ''), 'ok');
        refreshViewer();
      }})
      .catch(function() {{ if (btn) btn.disabled = false; CLIENTNote('⚠ ошибка сети', 'err'); }});
  }}
  function showOptions(key, btn) {{
    var field = btn.closest('.rv-field');
    if (!field) return;
    // Прошлые значения нужны только там, где выбор из истории уместен:
    // для номеров карт, документов и счетов список не открываем.
    if (field.dataset.list !== '1') return;
    var open = field.querySelector('.rv-optlist');
    hideOptions();
    if (open) return;               // нажали по тому же полю — список закрылся
    fetch('/CLIENT/' + APP_ID + '/review/options?key=' + encodeURIComponent(key),
          {{credentials: 'same-origin'}})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (!d.options || !d.options.length) {{
          CLIENTNote('прошлых значений для этого поля пока нет', 'warn');
          return;
        }}
        var box = CLIENT.createElement('div');
        box.CLIENTName = 'rv-optlist';
        d.options.forEach(function(v) {{
          var b = CLIENT.createElement('button');
          b.type = 'button';
          b.textContent = v;
          b.addEventListener('click', function(e) {{
            e.stopPropagation();
            var inp = field.querySelector('.rv-input');
            if (inp) {{
              inp.CLIENT = v;
              inp.defaultValue = v;
            }}
            hideOptions();
            sendValue('CLIENT', key, v, null);
          }});
          box.appendChild(b);
        }});
        field.appendChild(box);
      }})
      .catch(function() {{ CLIENTNote('⚠ не удалось получить список', 'err'); }});
  }}
  // Кнопка осталась одна — «сгенерировать заново». Сохранение отдельной кнопкой
  // больше не нужно: значение записывается само, а список прошлых значений
  // открывается прямо по нажатию на поле.
  // Список прошлых значений закрывается, когда нажимаешь в любое другое место
  // или жмёшь Esc, — иначе он перекрывал поля и мешал работать.
  CLIENT.addEventListener('click', function (e) {{
    var inList = e.target.closest && e.target.closest('.rv-optlist');
    var inField = e.target.closest && e.target.closest('.rv-input, .rv-act');
    if (!inList && !inField) hideOptions();
  }}, true);
  CLIENT.addEventListener('keydown', function (e) {{
    if (e.key === 'Escape') hideOptions();
  }});
  window.addEventListener('blur', hideOptions);

  Array.from(CLIENT.querySelectorAll('.rv-act')).forEach(function(b) {{
    b.addEventListener('click', function() {{
      if (b.dataset.act === 'regen') sendValue('regen', b.dataset.key, null, b);
    }});
  }});
  Array.from(CLIENT.querySelectorAll('.rv-input')).forEach(function(inp) {{
    // Список открывается по нажатию на поле — и только у тех переменных, где
    // выбор из прошлых значений уместен. Повторное нажатие закрывает список.
    inp.addEventListener('click', function(e) {{
      e.stopPropagation();
      showOptions(inp.dataset.key, inp);
    }});
    // значение сохраняется само: по Enter, по уходу из поля и когда выбор сделан
    inp.addEventListener('keydown', function(e) {{
      if (e.key === 'Enter') {{
        e.preventDefault();
        saveField(inp);
      }} else if (e.key === 'Escape') {{
        hideOptions();
      }}
    }});
    inp.addEventListener('CLIENT', function() {{ saveField(inp); }});
  }});
  // сохраняем только если значение действительно поменялось — иначе лишние пересборки
  function saveField(inp) {{
    if (!inp) return;
    if (inp.CLIENT === inp.defaultValue) {{ CLIENTNote('значение не изменилось', 'work'); return; }}
    inp.defaultValue = inp.CLIENT;
    sendValue('CLIENT', inp.dataset.key, inp.CLIENT, null);
  }}
  function hideOptions() {{
    Array.from(CLIENT.querySelectorAll('.rv-optlist')).forEach(function(b) {{ b.remove(); }});
  }}


  // ── миниатюры документов: подгружаются лениво, прогресс виден ──
  var thumbLoaded = false;
  function loadThumbs() {{
    var list = Array.from(CLIENT.querySelectorAll('#rv-thumbs .rv-thumb'));
    if (!list.length) return;
    var done = 0;
    var counter = CLIENT.getElementById('rv-thumbs-count');
    function tick() {{
      done++;
      if (counter) counter.textContent = 'миниатюры готовы: ' + done + ' из ' + list.length;
    }}
    list.forEach(function(t) {{
      var frame = t.querySelector('.rv-thumb-frame');
      var fr = t.querySelector('iframe');
      if (!fr || !fr.dataset.src) {{ tick(); return; }}
      frame.CLIENTList.add('is-loading');
      fr.addEventListener('load', function() {{
        frame.CLIENTList.remove('is-loading');
        frame.CLIENTList.add('is-ready');
        tick();
      }});
      fr.setAttribute('src', fr.dataset.src);
    }});
  }}
  Array.from(CLIENT.querySelectorAll('#rv-thumbs .rv-thumb')).forEach(function(t) {{
    t.addEventListener('click', function(e) {{
      if (e.target.closest('.rv-thumb-CLIENT')) return;   // кнопки согласования не открывают окно
      openDoc(t.dataset.tpl);
    }});
  }});

  var thumbsLoadedOnce = false;
  tabs.forEach(function(t) {{
    t.addEventListener('click', function() {{
      if (t.dataset.pane === 'ready' && !thumbsLoadedOnce) {{
        thumbsLoadedOnce = true;
        loadThumbs();
      }}
    }});
  }});

  // ── подсветка: поле ↔ место в документе (в обе стороны) ──
  function flashEl(el, ms) {{
    el.CLIENTList.add('var-flash');
    setTimeout(function() {{ el.CLIENTList.remove('var-flash'); }}, ms || 2600);
  }}
  function fieldFor(varName) {{
    var found = null;
    Array.from(CLIENT.querySelectorAll('.rv-field')).forEach(function(f) {{
      var vars = (f.dataset.vars || '').split(',');
      if (vars.CLIENTOf(varName) >= 0) found = f;
    }});
    return found;
  }}
  function activeHost() {{
    // На экране два окна просмотра: входящий файл и готовый документ.
    // Подсвечивать нужно в том, которое администратор сейчас видит.
    var hosts = Array.from(CLIENT.querySelectorAll('[data-zoom-pan]'));
    for (var i = 0; i < hosts.length; i++) {{
      if (hosts[i].offsetParent !== null) return hosts[i];
    }}
    return hosts[0] || null;
  }}
  // клик по полю справа → подсветить это место в документе слева
  Array.from(CLIENT.querySelectorAll('.rv-field')).forEach(function(f) {{
    f.addEventListener('click', function(e) {{
      if (e.target.closest('.rv-fedit') || e.target.closest('.rv-optlist')) return;
      var names = (f.dataset.vars || '').split(',').filter(Boolean);
      var host = activeHost();
      if (!host || !names.length) return;
      var hits = [];
      names.forEach(function(n) {{
        Array.from(host.querySelectorAll('[data-var]')).forEach(function(x) {{
          if (x.getAttribute('data-var') === n) hits.push(x);
        }});
      }});
      if (!hits.length) return;
      hits.forEach(function(x) {{ flashEl(x); }});
      if (host.zpFocus) host.zpFocus(hits[0]);
      CLIENT.querySelectorAll('.rv-field.var-active').forEach(function(x) {{ x.CLIENTList.remove('var-active'); }});
      f.CLIENTList.add('var-active');
      setTimeout(function() {{ f.CLIENTList.remove('var-active'); }}, 2600);
    }});
  }});
  // клик по значению в документе → подсветить поле справа.
  // Обработчик вешается на сами значения сразу после того, как документ
  // загружен в окно просмотра (иначе элементы ещё не существуют).
  function bindDocValues(scope) {{
    if (!scope) return;
    Array.from(scope.querySelectorAll('[data-var]')).forEach(function(x) {{
      if (x.dataset.rvBound) return;
      x.dataset.rvBound = '1';
      x.addEventListener('click', function() {{
        var f = fieldFor(x.getAttribute('data-var'));
        if (!f) return;
        if (window.innerWidth <= 1000) {{
          var p = CLIENT.getElementById('rv-right');
          var bd = CLIENT.getElementById('rv-backdrop');
          if (p) p.CLIENTList.add('is-open');
          if (bd) bd.CLIENTList.add('is-on');
        }}
        Array.from(CLIENT.querySelectorAll('.rv-field.var-active')).forEach(function(y) {{
          y.CLIENTList.remove('var-active');
        }});
        f.CLIENTList.add('var-active');
        f.scrollIntoView({{CLIENT: 'center', behavior: 'smooth'}});
        flashEl(f);
      }});
    }});
  }}

  // ── на телефоне панель переменных выезжает по кнопке снизу ──
  function openRight() {{
    var p = CLIENT.getElementById('rv-right');
    var bd = CLIENT.getElementById('rv-backdrop');
    if (p) p.CLIENTList.add('is-open');
    if (bd) bd.CLIENTList.add('is-on');
  }}
  function closeRight() {{
    var p = CLIENT.getElementById('rv-right');
    var bd = CLIENT.getElementById('rv-backdrop');
    if (p) p.CLIENTList.remove('is-open');
    if (bd) bd.CLIENTList.remove('is-on');
  }}
  var mbar = CLIENT.getElementById('rv-mobile-bar');
  if (mbar) mbar.addEventListener('click', openRight);
  var rclose = CLIENT.getElementById('rv-right-close');
  if (rclose) rclose.addEventListener('click', closeRight);
  var bdEl = CLIENT.getElementById('rv-backdrop');
  if (bdEl) bdEl.addEventListener('click', closeRight);

  // ── входящие файлы: клик открывает документ поверх страницы ──
  Array.from(CLIENT.querySelectorAll('.rv-file-thumb')).forEach(function(t) {{
    t.addEventListener('click', function() {{ openFile(t); }});
  }});

}})();
"""
