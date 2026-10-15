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
  var tabs = Array.from(document.querySelectorAll('.rv-tab'));
  function showPane(key) {{
    tabs.forEach(function(x) {{ x.classList.toggle('is-on', x.dataset.pane === key); }});
    Array.from(document.querySelectorAll('.rv-pane')).forEach(function(p) {{
      p.classList.toggle('is-on', p.id === 'pane-' + key);
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
  var modal = document.getElementById('rv-modal');
  var mStage = document.getElementById('rv-modal-stage');
  var mTitle = document.getElementById('rv-modal-title');
  var mNote = document.getElementById('rv-modal-note');
  var mOk = document.getElementById('rv-modal-ok');
  var mNo = document.getElementById('rv-modal-no');
  var mTools = document.getElementById('rv-modal-tools');
  var modalTpl = null;          // какой документ открыт в окне (null — входящий файл)

  // Сбросить масштаб движка перед подстановкой нового содержимого: сам движок
  // помнит масштаб от прошлого файла, из-за чего новый показывался его размером.
  function resetZoom() {{
    var host = document.querySelector('#rv-modal [data-zoom-pan]');
    if (!host || !host.parentNode) return;
    var f = host.parentNode.querySelector('[data-zp="fit"]');
    if (f) f.click();
  }}

  // Вписать содержимое окна целиком — и по ширине, и по высоте. Работаем кнопками
  // самого движка просмотра (его код не меняем): он умеет только «по ширине», поэтому
  // при высоком листе документ обрубался снизу.
  function fitInside() {{
    var host = document.querySelector('#rv-modal [data-zoom-pan]');
    if (!host) return false;
    var canvas = host.querySelector('.zp-canvas');
    var shell = host.parentNode;
    var out = shell ? shell.querySelector('[data-zp="out"]') : null;
    if (!canvas || !out) return false;
    var body = document.querySelector('#rv-modal .rv-modal-body');
    if (!body) return false;
    var availW = body.clientWidth - 24;
    var availH = body.clientHeight - 56;      // минус строка масштаба над содержимым
    if (availW < 60 || availH < 80) return false;
    var guard = 0;
    function rect() {{ return canvas.getBoundingClientRect(); }}
    while (guard < 20 && (rect().height > availH || rect().width > availW)) {{
      var before = rect().width;
      out.click();
      guard++;
      if (rect().width >= before - 0.5) break;   // масштаб больше не меняется
    }}
    return true;
  }}
  function fitSoon() {{ [250, 700, 1400, 2400].forEach(function(t) {{ setTimeout(fitInside, t); }}); }}
  var bFit = document.getElementById('rv-modal-fit');
  if (bFit) bFit.addEventListener('click', function() {{ fitInside(); }});

  // При смене содержимого пересобираем зону просмотра целиком: движок держит
  // масштаб и содержимое прошлого файла, поэтому новый показывался его размером.
  // Новый контейнер создаём вместе с меткой движка — он подхватит его сам.
  function resetStage() {{
    var old = document.querySelector('#rv-modal [data-zoom-pan]');
    if (!old) return null;
    var shell = old.closest('.zp-shell') || old;
    var parent = shell.parentNode;
    if (!parent) return null;
    var host = document.createElement('div');
    host.className = 'zp-preview';
    host.setAttribute('data-zoom-pan', '');
    var stage = document.createElement('div');
    stage.className = 'html-stage';
    stage.id = 'rv-modal-stage';
    host.appendChild(stage);
    parent.replaceChild(host, shell);
    mStage = stage;
    if (window.zpScan) window.zpScan(parent);
    return stage;
  }}



  // Документ в окне показываем по ширине окна: если лист уже окна, увеличиваем —
  // иначе маленький скан (паспорт, фото) висит посреди пустого поля.
  function fitWidth() {{
    var body = document.querySelector('#rv-modal .rv-modal-body');
    if (!body) return 0;
    resetZoom();                       // базовый масштаб по ширине
    var avail = body.clientWidth - 26;
    var plus = document.querySelector('#rv-modal [data-zp="in"]');
    if (!plus) return 0;
    var minus = document.querySelector('#rv-modal [data-zp="out"]');
    var steps = 0;
    while (steps < 14) {{
      var c = document.querySelector('#rv-modal .zp-canvas');
      if (!c) break;
      var w = c.getBoundingClientRect().width;
      // заполнили ширину — хватит; шаг движка крупный (1.2), поэтому проверяем,
      // что после него документ не станет шире окна
      if (!w || w >= avail * 0.92) break;
      if (w * 1.2 > avail) break;
      plus.click();
      steps++;
    }}
    // страховка: если всё-таки вышли за ширину окна — возвращаем шаг назад
    var c2 = document.querySelector('#rv-modal .zp-canvas');
    if (minus && c2 && c2.getBoundingClientRect().width > avail + 2) minus.click();
    return steps;
  }}


  // Инструкция по переменной — под маленьким кружочком «i»: нажатие открывает
  // окно поверх страницы, текст берётся из правила переменной в конструкторе.
  function showInstr(btn) {{
    var back = document.getElementById('rv-instr-back');
    if (!back) {{
      back = document.createElement('div');
      back.id = 'rv-instr-back';
      back.className = 'rv-instr-back';
      back.innerHTML = '<div class="rv-instr-win"><div class="rv-instr-head">' +
        '<span id="rv-instr-title">Инструкция</span>' +
        '<button type="button" id="rv-instr-close" title="Закрыть">✕</button></div>' +
        '<div class="rv-instr-body" id="rv-instr-body"></div>' +
        '<div class="rv-instr-meta" id="rv-instr-meta"></div></div>';
      document.body.appendChild(back);
      back.addEventListener('click', function (e) {{
        if (e.target === back) hideInstr();
      }});
      var x = document.getElementById('rv-instr-close');
      if (x) x.addEventListener('click', hideInstr);
    }}
    var field = btn.closest('.rv-field');
    var label = field ? (field.querySelector('.rv-lname') || {{}}).textContent || '' : '';
    var rule = btn.dataset.rule || '';
    var meta = field && field.querySelector('.rv-fmeta') ? field.querySelector('.rv-fmeta').textContent : '';
    var t = document.getElementById('rv-instr-title');
    var bd = document.getElementById('rv-instr-body');
    var mt = document.getElementById('rv-instr-meta');
    if (t) t.textContent = label.trim();
    if (bd) bd.textContent = rule || ruleFallback(field);
    if (mt) mt.textContent = meta;
    back.classList.add('is-on');
  }}
  function ruleFallback(field) {{
    if (!field) return 'Правило для этой переменной не задано.';
    if (field.dataset.list === '1') return 'Значение можно вписать руками или выбрать из прошлых значений.';
    var badge = field.querySelector('.rv-rule');
    var t = badge ? badge.textContent : '';
    if (t.indexOf('клиента') >= 0) return 'Значение берётся из карточки клиента.';
    if (t.indexOf('одинаково') >= 0) return 'Одно значение на все документы заявки.';
    return 'Значение подставляется автоматически; кнопка 🎲 перевыпускает его заново.';
  }}
  function hideInstr() {{
    var back = document.getElementById('rv-instr-back');
    if (back) back.classList.remove('is-on');
  }}
  document.addEventListener('click', function (e) {{
    var b = e.target.closest ? e.target.closest('.rv-info') : null;
    if (!b) return;
    e.preventDefault();
    e.stopPropagation();
    showInstr(b);
  }}, true);
  document.addEventListener('keydown', function (e) {{
    if (e.key === 'Escape') hideInstr();
  }});


  // ── Раскрывающиеся разделы панели: нажатие на заголовок закрывает и открывает
  document.addEventListener('click', function (e) {{
    var h = e.target.closest ? e.target.closest('.rv-blk-head') : null;
    if (h) {{
      var sec = h.parentNode;
      if (sec) sec.classList.toggle('is-closed');
      return;
    }}
    var all = e.target.closest ? e.target.closest('#rv-collapse-all') : null;
    if (all) {{
      var secs = Array.from(document.querySelectorAll('.rv-right .rv-blk'));
      var anyOpen = secs.some(function (s) {{ return !s.classList.contains('is-closed'); }});
      secs.forEach(function (s) {{ s.classList.toggle('is-closed', anyOpen); }});
      all.textContent = anyOpen ? 'Раскрыть блоки' : 'Свернуть блоки';
    }}
  }});

  // ── Поиск переменной и строка «Требует внимания» (по рендеру правой колонки) ──
  var varsSearch = document.getElementById('rv-vars-search');
  function applyVarsFilter() {{
    var q = ((varsSearch && varsSearch.value) || '').trim().toLowerCase();
    var shown = 0;
    Array.from(document.querySelectorAll('.rv-right .rv-field')).forEach(function (f) {{
      var hay = ((f.dataset.var || '') + ' ' + (f.dataset.vars || '') + ' ' + f.innerText).toLowerCase();
      var ok = !q || hay.indexOf(q) >= 0;
      f.classList.toggle('is-hidden', !ok);
      if (ok) shown++;
    }});
    Array.from(document.querySelectorAll('.rv-right .rv-blk')).forEach(function (b) {{
      var any = Array.from(b.querySelectorAll('.rv-field')).some(function (f) {{
        return !f.classList.contains('is-hidden');
      }});
      b.classList.toggle('is-hidden', !any);
    }});
    var cnt = document.getElementById('rv-panel-count');
    if (cnt) cnt.textContent = q ? ('найдено переменных: ' + shown) : '';
  }}
  if (varsSearch) {{
    varsSearch.addEventListener('input', applyVarsFilter);
    varsSearch.addEventListener('search', applyVarsFilter);
  }}
  // «Проверить и исправить» ведёт к первому проблемному полю и подсвечивает его.
  var attnBtn = document.getElementById('rv-attn-btn');
  if (attnBtn) attnBtn.addEventListener('click', function () {{
    var bad = document.querySelector('.rv-right .rv-field.is-conflict')
           || document.querySelector('.rv-right .rv-field.is-empty')
           || document.querySelector('.rv-right .rv-field');
    if (!bad) return;
    var blk = bad.closest ? bad.closest('.rv-blk') : null;
    if (blk) blk.classList.remove('is-closed');
    bad.scrollIntoView({{behavior: 'smooth', block: 'center'}});
    bad.classList.add('is-flash');
    setTimeout(function () {{ bad.classList.remove('is-flash'); }}, 1800);
  }});

  // Поле подстраивается под текст: длинный адрес видно целиком, без прокрутки
  function fitInput(el) {{
    if (!el) return;
    el.style.height = 'auto';
    var h = Math.max(34, el.scrollHeight);
    el.style.height = h + 'px';
  }}
  document.addEventListener('input', function (e) {{
    if (e.target.classList && e.target.classList.contains('rv-input')) fitInput(e.target);
  }});
  function fitAll() {{
    Array.from(document.querySelectorAll('.rv-right .rv-input')).forEach(fitInput);
    Array.from(document.querySelectorAll('.rv-right .rv-input')).forEach(function (el) {{
      el.classList.toggle('is-empty', !el.value.trim());
    }});
  }}
  document.addEventListener('focusin', function (e) {{
    if (e.target.classList && e.target.classList.contains('rv-input')) fitInput(e.target);
  }});

  // Счётчик заполнения: красным, пока заполнено не всё; зелёным с галочкой, когда всё
  function refreshProgress() {{
    var box = document.querySelector('.rv-right');
    if (!box) return;
    var fields = Array.from(box.querySelectorAll('.rv-field'));
    var filled = fields.filter(function (f) {{
      var i = f.querySelector('.rv-input');
      return i && i.value.trim();
    }}).length;
    var box2 = document.getElementById('rv-progress');
    var txt = document.getElementById('rv-progress-text');
    if (!box2 || !txt) return;
    if (fields.length && filled === fields.length) {{
      box2.classList.add('is-done');
      box2.classList.remove('is-urgent');
      txt.textContent = 'Заполнено всё: ' + filled + ' из ' + fields.length;
    }} else {{
      box2.classList.remove('is-done');
      box2.classList.add('is-urgent');
      txt.textContent = 'Заполнено ' + filled + ' из ' + fields.length;
    }}
    fields.forEach(function (f) {{
      var i = f.querySelector('.rv-input');
      if (i) i.classList.toggle('is-empty', !i.value.trim());
    }});
  }}
  window.__rvFit = fitAll;
  window.__rvProgress = refreshProgress;
  document.addEventListener('DOMContentLoaded', function () {{ fitAll(); refreshProgress(); }});
  setTimeout(function () {{ fitAll(); refreshProgress(); }}, 400);

  // Связь переменной в панели и её значения в документе. Нажал на переменную —
  // она подсвечена в панели и её место подсвечено в документе; нажал на значение
  // в документе — подсветилась та же переменная справа.
  var pickedVar = null;

  function stageRoots() {{
    return Array.from(document.querySelectorAll('#rv-modal .html-stage'));
  }}

  function clearStageMarks() {{
    stageRoots().forEach(function(root) {{
      Array.from(root.querySelectorAll('[data-var].is-picked')).forEach(function(el) {{
        el.classList.remove('is-picked');
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
        if (el) {{ el.classList.add('is-picked'); hits++; }}
      }});
    }});
    // подсвеченное место показываем в окне
    var first = document.querySelector('#rv-modal .html-stage [data-var].is-picked');
    if (first && first.scrollIntoView) {{
      try {{ first.scrollIntoView({{ block: 'center', inline: 'nearest' }}); }} catch (e) {{}}
    }}
    return hits;
  }}

  function fieldsOfVar(name) {{
    return Array.from(document.querySelectorAll('.rv-right .rv-field')).filter(function(f) {{
      return (f.dataset.vars || '').split(',').indexOf(name) >= 0;
    }});
  }}

  function pickVarFromPanel(field) {{
    if (!field) return;
    Array.from(document.querySelectorAll('.rv-field.is-active')).forEach(function(f) {{
      f.classList.remove('is-active');
    }});
    field.classList.add('is-active');
    pickedVar = (field.dataset.vars || '').split(',').filter(Boolean);
    var hits = markInStage(pickedVar);
    field.classList.toggle('is-linked', hits > 0);
  }}

  function pickVarFromStage(el) {{
    var name = el.getAttribute('data-var');
    if (!name) return;
    clearStageMarks();
    el.classList.add('is-picked');
    var fields = fieldsOfVar(name);
    Array.from(document.querySelectorAll('.rv-field.is-active')).forEach(function(f) {{
      f.classList.remove('is-active');
    }});
    if (!fields.length) return;
    fields.forEach(function(f) {{ f.classList.add('is-active'); }});
    var f = fields[0];
    if (f.scrollIntoView) {{
      try {{ f.scrollIntoView({{ block: 'center', behavior: 'smooth' }}); }} catch (e) {{}}
    }}
  }}

  // Редактор переменной прямо из документа: на телефоне нажатие на переменную
  // в нашем документе открывает панель переменных снизу и ставит курсор в это поле,
  // чтобы значение можно было выбрать из прошлых, сгенерировать заново или написать.
  function openVarEditor(name) {{
    if (!name) return;
    if (window.innerWidth > 860) return;          // на большом экране панель и так рядом
    var fields = fieldsOfVar(name);
    if (!fields.length) return;
    if (typeof openRight === 'function') openRight();
    var f = fields[0];
    setTimeout(function() {{
      var p = document.getElementById('rv-right');
      if (p && p.scrollTop !== undefined) {{
        try {{ p.scrollTop = Math.max(0, f.offsetTop - 90); }} catch (e) {{}}
      }}
      var inp = f.querySelector('.rv-input');
      if (inp) {{ try {{ inp.focus({{ preventScroll: true }}); }} catch (e) {{}} }}
    }}, 320);
  }}

  // нажатие на переменную в панели — держим подсветку, пока в ней работаешь
  document.addEventListener('focusin', function(e) {{
    var f = e.target.closest ? e.target.closest('.rv-field') : null;
    if (f) pickVarFromPanel(f);
  }});
  document.addEventListener('click', function(e) {{
    var f = e.target.closest ? e.target.closest('.rv-field') : null;
    if (f) pickVarFromPanel(f);
    // нажатие на значение в документе
    var v = e.target.closest ? e.target.closest('#rv-modal .html-stage [data-var]') : null;
    if (v) {{ e.preventDefault(); pickVarFromStage(v); openVarEditor(v.getAttribute('data-var')); }}
  }});

  // ── Мобильная карточка заявки: сворачивание шапки с информацией о заявке
  document.addEventListener('click', function(e) {{
    var t = e.target.closest ? e.target.closest('.rv-head-toggle') : null;
    if (!t) return;
    e.preventDefault();
    var head = t.closest('.rv-head');
    if (head) head.classList.toggle('is-collapsed');
  }});



  function saveDrive(url) {{
    var fd = new FormData();
    fd.append('url', url);
    fetch('/applications/' + APP_ID + '/review/drive',
          {{method: 'POST', body: fd, credentials: 'same-origin',
            headers: {{'X-Requested-With': 'fetch'}}}})
      .then(function (r) {{ return r.json(); }})
      .then(function (d) {{
        valueNote(d && d.ok ? 'Ссылка на папку заявки сохранена' : ('⚠ ' + ((d && d.error) || 'не сохранилось')),
                  d && d.ok ? 'ok' : 'warn');
      }});
  }}
  var bDrive = document.getElementById('rv-drive-save');
  if (bDrive) {{
    bDrive.addEventListener('click', function () {{
      var inp = document.getElementById('rv-drive-input');
      var url = inp ? inp.value.trim() : '';
      if (!url) {{ valueNote('Вставьте ссылку на папку заявки на Google Drive', 'warn'); return; }}
      saveDrive(url);
    }});
  }}
  var bDriveEdit = document.getElementById('rv-drive-edit');
  if (bDriveEdit) {{
    bDriveEdit.addEventListener('click', function () {{
      var box = document.getElementById('rv-drive-box');
      if (box) {{
        box.innerHTML = '<input type="text" id="rv-drive-input" placeholder="вставьте ссылку на папку заявки на Drive">' +
                        '<button type="button" class="btn sm" id="rv-drive-save">Прикрепить</button>';
        var b = document.getElementById('rv-drive-save');
        if (b) b.addEventListener('click', function () {{
          var inp = document.getElementById('rv-drive-input');
          if (inp && inp.value.trim()) saveDrive(inp.value.trim());
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
               tile.querySelector('.rv-thumb-tools') || tile.querySelector('.rv-thumb-frame');
    if (!host) return null;
    dot = document.createElement('span');
    dot.className = 'rv-tile-dot';
    dot.title = 'Готовлю миниатюру для полного просмотра…';
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
    if (tpl) return {{url: '/applications/' + APP_ID + '/doc/' + tpl + '/html', kind: 'frame'}};
    return null;
  }}
  function warmTile(tile) {{
    var dot = tileDot(tile);
    if (!dot || dot.dataset.done === '1') return;
    var t = tileUrl(tile);
    if (!t) {{ dot.classList.add('is-cached'); dot.dataset.done = '1'; return; }}
    if (t.kind === 'doc') {{
      // Документ — тяжёлый (сервер собирает HTML): заранее не тянем, грузится
      // при открытии. Иначе открытие заявки превращалось в пачку тяжёлых сборок.
      dot.classList.add('is-cached');
      dot.dataset.done = '1';
      dot.title = 'Откроется по нажатию';
      return;
    }}
    var ok = function () {{
      dot.classList.add('is-cached');
      dot.dataset.done = '1';
      dot.title = 'Готово к просмотру — откроется сразу';
    }};
    var bad = function () {{
      dot.classList.add('is-failed');
      dot.dataset.done = '1';
      dot.title = 'Не удалось подготовить — откроется при нажатии';
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
  function warmAllTiles(opts) {{
    // Прогреваем только то, что видно на экране, и по одной плитке за раз:
    // одновременная пачка запросов по всем плиткам и документам забивала
    // сервер, и страница заявки «тупила» при открытии.
    var onlyVisible = !opts || opts.visible !== false;
    var tiles = Array.from(document.querySelectorAll('.rv-thumb'));
    if (onlyVisible) {{
      var vh = window.innerHeight || 800;
      tiles = tiles.filter(function (t) {{
        var r = t.getBoundingClientRect();
        return r.top < vh + 300 && r.bottom > -300;
      }});
    }}
    var i = 0;
    (function next() {{
      if (i >= tiles.length) return;
      var t = tiles[i++];
      var u = tileUrl(t);
      if (u && u.kind !== 'doc') warmTile(t);      // документы греются по нажатию
      setTimeout(next, 150);
    }})();
  }}
  // Фоновый прогрев плиток больше не нужен: миниатюры грузятся нативно
  // (лёгкие копии, 5 КБ), а бланки — только активный. Лишние запросы убраны.
  Array.from(document.querySelectorAll('.rv-tab')).forEach(function(t) {{
    t.addEventListener('click', function () {{ setTimeout(function () {{ warmAllTiles(); }}, 250); }});
  }});

  // Колёсико загрузки на плитках: пока файл не отрисован, крутится; после загрузки
  // или ошибки — прячем и показываем саму миниатюру.
  function wireTileLoad(tile) {{
    var frame = tile.querySelector('.rv-thumb-frame');
    if (!frame || frame.dataset.wired === '1') return;
    frame.dataset.wired = '1';
    var done = function () {{
      frame.classList.add('is-ready');
      frame.classList.remove('is-loading');
    }};
    var media = frame.querySelector('img, iframe');
    if (!media) {{ done(); return; }}
    if (media.tagName === 'IMG') {{
      // Миниатюра — картинка на пару десятков килобайт: грузим сразу все плитки.
      var src = media.dataset.src || media.getAttribute('src');
      if (src && media.getAttribute('src') !== src) media.setAttribute('src', src);
      if (media.complete && media.naturalWidth > 0) {{ done(); return; }}
      media.addEventListener('load', done);
      media.addEventListener('error', done);
      // если картинка тянется с диска долго — не оставляем колёсико навсегда
      setTimeout(function () {{ if (!media.naturalWidth) done(); }}, 15000);
    }} else {{
      media.addEventListener('load', done);
      // Тянуть сразу все бланки — это серверная сборка каждого документа, из-за
      // неё страница «тупила». Грузим только активный (он же в большом окне),
      // остальные — по нажатию.
      if (tile.classList.contains('is-on')) {{
        var src = media.dataset.src || media.getAttribute('src');
        if (src && media.getAttribute('src') !== src) media.setAttribute('src', src);
      }} else {{
        done();
      }}
    }}
  }}
  function wireAllTiles() {{
    Array.from(document.querySelectorAll('.rv-thumb')).forEach(wireTileLoad);
  }}
  wireAllTiles();
  Array.from(document.querySelectorAll('.rv-tab')).forEach(function(t) {{
    t.addEventListener('click', function () {{ setTimeout(wireAllTiles, 60); }});
  }});

  function openModal() {{
    if (!modal) return;
    modal.classList.add('is-on');
    document.documentElement.style.overflow = 'hidden';
    // Панель переменных поднимается вместе с окном: пока документ открыт, она
    // занимает правую часть экрана от самого верха.
    document.body.classList.add('rv-viewing');
  }}
  function closeModal() {{
    document.body.classList.remove('rv-viewing');
    if (!modal) return;
    modal.classList.remove('is-on');
    document.documentElement.style.overflow = '';
    modalTpl = null;
    filterByDoc(null);
  }}
  // содержимое окна: документ заявки или входящий файл клиента
  function loadInto(tpl) {{
    if (!mStage) return;
    var _empty = document.getElementById('rv-view-empty');
    if (_empty) _empty.style.display = 'none';
    mStage.classList.remove('is-image');    // документ — лист фиксированной ширины
    resetStage();                          // чистая зона: без масштаба прошлого файла
    mStage.innerHTML = '<div class="rv-loading"><span class="rv-spinner"></span>' +
                       '<span>загружаю документ…</span></div>';
    if (!tpl) return;
    fetch('/applications/' + APP_ID + '/doc/' + tpl + '/html', {{credentials: 'same-origin'}})
      .then(function(r) {{ return r.text(); }})
      .then(function(html) {{
        if (!html || html.indexOf('<') === -1) {{
          mStage.innerHTML = '<div class="rv-empty">Документ ещё не сформирован — соберите его на старом экране.</div>';
          return;
        }}
        // HTML документа формирует наш сервер по шаблону — источник доверенный
        mStage.innerHTML = html;
        bindDocValues(mStage);       // подсветка: значение в документе ↔ поле справа
        fitWidth();                  // документ по ширине окна, маленький — увеличиваем
        window.dispatchEvent(new Event('resize'));
      }})
      .catch(function() {{
        mStage.innerHTML = '<div class="rv-empty">Не удалось открыть документ.</div>';
      }});
  }}
  // Фильтр панели переменных: показываем только то, что относится к открытому
  // документу. Открыл другой документ — список переменных поменялся.
  var filterMode = 'doc';   // всегда показываем переменные открытого документа
  function filterByDoc(tpl) {{
    var box = document.querySelector('.rv-right .rv-body');
    if (!box) return 0;
    var fields = Array.from(box.querySelectorAll('.rv-field'));
    var shown = 0;
    fields.forEach(function(f) {{
      var t = (f.dataset.tpls || '').split(',');
      var mine = !!(tpl && t.indexOf(String(tpl)) >= 0);
      // Документ не открыт — показываем весь список; открыт — только его переменные.
      var show = !tpl || mine;
      f.style.display = show ? '' : 'none';
      f.classList.toggle('is-doc', mine && filterMode === 'doc');
      if (show) shown++;
    }});
    var cnt = document.getElementById('rv-panel-count');
    if (cnt) cnt.textContent = tpl
      ? ('переменных этого документа: ' + shown)
      : ('переменных: ' + fields.length);
    var head = document.getElementById('rv-panel-note');
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
    var box = document.querySelector('.rv-right .rv-body');
    if (!box) return 0;
    var list = (names || []);
    var fields = Array.from(box.querySelectorAll('.rv-field'));
    if (!list.length) {{ filterByDoc(null); return 0; }}
    var shown = 0;
    fields.forEach(function(f) {{
      var mine = (f.dataset.vars || '').split(',').some(function(n) {{
        return list.indexOf(n) >= 0;
      }});
      f.style.display = mine ? '' : 'none';
      f.classList.toggle('is-doc', mine);
      if (mine) shown++;
    }});
    var cnt = document.getElementById('rv-panel-count');
    if (cnt) cnt.textContent = (label || 'переменных из этого документа') + ': ' + shown;
    if (box.scrollTo) box.scrollTop = 0;
    return shown;
  }}
  // Переключателя нет: панель сама показывает переменные открытого документа.

  // открыть документ заявки: в окне появляются кнопки согласования
  // Подпись в шапке окна просмотра: строка источника и ссылка на оригинал.
  var mSrc = document.getElementById('rv-modal-src');
  var mDl = document.getElementById('rv-modal-dl');
  function setModalSource(text, href, label) {{
    if (mSrc) mSrc.textContent = text || '';
    if (mDl) {{
      if (href) {{ mDl.href = href; mDl.textContent = label || 'Скачать оригинал'; mDl.hidden = false; }}
      else {{ mDl.hidden = true; }}
    }}
  }}
  function openDoc(tpl) {{
    var tile = null;
    Array.from(document.querySelectorAll('#rv-thumbs .rv-thumb')).forEach(function(x) {{
      if (String(x.dataset.tpl) === String(tpl)) tile = x;
    }});
    modalTpl = tpl;
    if (mTitle) mTitle.textContent = tile ? (tile.querySelector('.rv-thumb-name') || {{}}).textContent : ('Документ ' + tpl);
    if (mTools) mTools.style.display = '';
    if (mOk) mOk.style.display = '';
    if (mNo) mNo.style.display = '';
    var st = document.getElementById('rv-thumb-status-' + tpl);
    if (mNote) mNote.textContent = 'Справа — переменные этого документа. Поправите значение — документ пересоберётся.';
    Array.from(document.querySelectorAll('#rv-thumbs .rv-thumb')).forEach(function(x) {{
      x.classList.toggle('is-on', String(x.dataset.tpl) === String(tpl));
    }});
    openModal();
    loadInto(tpl);
    var n = filterByDoc(tpl);
    pickedVar = null; clearStageMarks();
    setModalSource('Собран из шаблона · переменных: ' + n,
                   '/applications/' + APP_ID + '/doc/' + tpl + '/html', 'Открыть оригинал');
    if (mNote) mNote.textContent = 'Справа — переменные этого документа (' + n + ' шт.): '
      + 'они подсвечены и подняты наверх. Поправите значение — документ пересоберётся.';
  }}
  // открыть входящий файл: кнопки согласования не нужны
  function openFile(tile) {{
    var frame = tile.querySelector('.rv-thumb-frame');
    var _empty2 = document.getElementById('rv-view-empty');
    if (_empty2) _empty2.style.display = 'none';
    var img = frame ? frame.querySelector('img') : null;
    var fr = frame ? frame.querySelector('iframe') : null;
    var url = img ? (img.getAttribute('src') || img.dataset.src)
                  : (fr ? (fr.dataset.src || fr.getAttribute('src')) : null);
    if (tile.dataset.page) url = tile.dataset.page;   // PDF клиента — страницей картинкой
    if (!url) {{ valueNote('этот файл нельзя показать в браузере — скачайте его с Google Drive', 'warn'); return; }}
    modalTpl = null;
    if (mTitle) mTitle.textContent = tile.dataset.file || 'Входящий документ';
    // Скрываем только согласование: «Закрыть» должно остаться всегда, иначе
    // из просмотра файла не выйти.
    if (mOk) mOk.style.display = 'none';
    if (mNo) mNo.style.display = 'none';
    if (mNote) mNote.textContent = 'Входящий документ с Google Drive. Справа — переменные, которые из него вытащены.';
    setModalSource('Скан клиента · файл из папки клиента на Google Диске',
                   '/applications/' + APP_ID + '/file?name=' + encodeURIComponent(tile.dataset.file || ''),
                   'Скачать оригинал');
    if (mStage) {{
      // Входящий файл показываем как снимок: ширину листа A4 здесь не задаём
      resetStage();
      mStage.classList.add('is-image');
      // Снимок с диска приходит не мгновенно: показываем колёсико, пока файл
      // не загрузился, и только потом ставим картинку и подгоняем по ширине.
      mStage.innerHTML = '<div class="rv-loading"><span class="rv-spinner"></span>' +
        '<div>Загружаю ' + (img ? 'снимок' : 'документ') + '…</div></div>';
      if (img) {{
        var probe = new Image();
        probe.onload = function () {{
          mStage.innerHTML = '<img src="' + url + '" alt="">';
          fitWidth();
        }};
        probe.onerror = function () {{
          mStage.innerHTML = '<div class="rv-loading"><div>файл не открылся в браузере — ' +
            'скачайте его с Google Drive</div></div>';
        }};
        probe.src = url;
      }} else {{
        var fr2 = document.createElement('iframe');
        fr2.setAttribute('title', 'Входящий документ');
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
      var cnt0 = document.getElementById('rv-panel-count');
      if (cnt0) cnt0.textContent = 'определяю переменные этого документа…';
      fetch('/applications/' + APP_ID + '/review/file-vars?name=' + encodeURIComponent(fileName),
            {{credentials: 'same-origin'}})
        .then(function (r) {{ return r.json(); }})
        .then(function (d) {{
          if (!d || !d.ok) {{ filterByDoc(null); return; }}
          if (d.vars && d.vars.length) {{
            filterByVars(d.vars, 'переменных из этого документа');
          }} else {{
            filterByDoc(null);
            var c = document.getElementById('rv-panel-count');
            if (c) c.textContent = 'из этого документа переменные не распознаны — показаны все';
          }}
        }})
        .catch(function () {{ filterByDoc(null); }});
    }}
  }}
  // ── действия по документам: разбор с Google Drive и автозаполнение ──
  function runAction(btn, url, label, question) {{
    if (!btn) return;
    if (question && !window.confirm(question)) return;
    var was = btn.textContent;
    btn.disabled = true;
    btn.textContent = label + '…';
    valueNote(label + '…', 'work');
    fetch(url, {{method: 'POST', credentials: 'same-origin',
                 headers: {{'X-Requested-With': 'fetch'}}}})
      .then(function(r) {{ return r.json().catch(function() {{ return {{}}; }}); }})
      .then(function(d) {{
        btn.disabled = false;
        btn.textContent = was;
        if (d && d.error) {{ valueNote('⚠ ' + d.error, 'err'); return; }}
        var tail = (d && d.found !== undefined) ? (' · найдено значений: ' + d.found)
                 : (d && d.done !== undefined) ? (' · документов собрано: ' + d.done) : '';
        valueNote('✅ ' + label + ': готово' + tail + '. Обновляю экран…', 'ok');
        // данные изменились — показываем экран заново, уже с новыми значениями
        setTimeout(function() {{ location.reload(); }}, 1200);
      }})
      .catch(function() {{
        btn.disabled = false;
        btn.textContent = was;
        valueNote('⚠ не удалось выполнить: ' + label, 'err');
      }});
  }}
  // ── Два шага заявки: разбор документов и заполнение полей ───────────────
  // Работают сами при заходе администратора. Значок на кнопке показывает,
  // что шаг выполнен (галочка) или идёт сейчас (кружок крутится). Нажать можно
  // и вручную — если был сбой, шаг повторится.
  var bScan = document.getElementById('rv-scan');
  var bFill = document.getElementById('rv-autofill');

  function stepRun(btn, url, label, then) {{
    if (!btn) {{ if (then) then(); return; }}
    // кнопка визуально нажимается сама — видно, что этап пошёл автоматически
    btn.classList.add('is-press');
    setTimeout(function () {{ btn.classList.remove('is-press'); }}, 460);
    btn.classList.add('is-busy');
    btn.disabled = true;
    fetch(url, {{method: 'POST', credentials: 'same-origin',
                 headers: {{'X-Requested-With': 'fetch'}}}})
      .then(function (r) {{ return r.json().catch(function () {{ return {{}}; }}); }})
      .then(function (d) {{
        btn.classList.remove('is-busy');
        btn.disabled = false;
        if (d && d.error) {{
          // не получилось — галочки нет, администратор нажмёт сам
          valueNote('⚠ ' + label + ': ' + d.error, 'err');
          return;
        }}
        btn.dataset.done = '1';
        valueNote('✅ ' + label + ': готово', 'ok');
        if (then) then();
      }})
      .catch(function () {{
        btn.classList.remove('is-busy');
        btn.disabled = false;
        valueNote('⚠ ' + label + ': не удалось', 'err');
      }});
  }}

  // Подпись под кнопками: что реально происходит с Google Диском клиента
  function scanNote(text, warn) {{
    var el = document.getElementById('rv-scan-note');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('is-warn', !!warn);
  }}

  // Первый шаг: идём в папку клиента, достаём документы и читаем значения.
  // Галочка встаёт только тогда, когда документы действительно скачаны и прочитаны;
  // второй шаг (заполнение) запускается после этого и не раньше.
  function stepScan(then, force) {{
    if (!bScan) {{ if (then) then(); return; }}
    bScan.classList.add('is-press');
    setTimeout(function () {{ bScan.classList.remove('is-press'); }}, 460);
    bScan.classList.add('is-busy');
    bScan.disabled = true;
    scanNote(force ? 'идём в папку клиента заново — сверяем документы и считаем по ним заново…'
                   : 'идём в папку клиента на Google Диске — достаём документы…', false);
    fetch('/applications/' + APP_ID + '/drive-scan' + (force ? '?force=1' : ''),
          {{method: 'POST', credentials: 'same-origin',
            headers: {{'X-Requested-With': 'fetch'}}}})
      .then(function (r) {{ return r.json().catch(function () {{ return {{}}; }}); }})
      .then(function (d) {{
        if (d && d.ok === false) {{
          // документы не достали — галочки нет, показываем причину
          bScan.classList.remove('is-busy');
          bScan.disabled = false;
          scanNote('⚠ ' + (d.note || 'не удалось прочитать документы с Google Диска'), true);
          valueNote('⚠ Документы не разобраны: ' + (d.note || 'нет данных'), 'err');
          return;
        }}
        scanWatch(then);
      }})
      .catch(function () {{
        bScan.classList.remove('is-busy');
        bScan.disabled = false;
        scanNote('⚠ не удалось связаться с Google Диском', true);
      }});
  }}

  // Следим за разбором: индикатор крутится, пока документы качаются и читаются.
  // Разбор — долгий (скачивание + чтение каждого файла), поэтому опрашиваем состояние.
  function scanWatch(then) {{
    var tries = 0, MAX = 90;   // до ~6 минут ожидания
    (function poll() {{
      fetch('/applications/' + APP_ID + '/review/scan-status',
            {{credentials: 'same-origin', headers: {{'X-Requested-With': 'fetch'}}}})
        .then(function (r) {{ return r.json().catch(function () {{ return {{}}; }}); }})
        .then(function (d) {{
          if (d && d.ok) {{
            bScan.classList.remove('is-busy');
            bScan.disabled = false;
            bScan.dataset.done = '1';
            scanNote('документы клиента получены и прочитаны: ' + (d.files || d.done || 0), false);
            valueNote('✅ Документы разобраны: ' + (d.files || d.done || 0), 'ok');
            if (then) then();
            return;
          }}
          // разбор упал или документов в папке нет — не ждём впустую, показываем причину
          if (d && d.status === 'fail') {{
            bScan.classList.remove('is-busy');
            bScan.disabled = false;
            scanNote('⚠ ' + (d.note || 'на Google Диске клиента документов не нашлось'), true);
            return;
          }}
          if (++tries > MAX) {{
            bScan.classList.remove('is-busy');
            bScan.disabled = false;
            scanNote('⚠ ' + ((d && d.note) || 'Google Диск пока не отдал документы'), true);
            return;
          }}
          scanNote('читаем документы клиента: ' + ((d && d.done) || 0) + ' из ' + ((d && d.total) || 0) + '…', false);
          setTimeout(poll, 4000);
        }})
        .catch(function () {{ if (++tries > MAX) {{ bScan.classList.remove('is-busy'); }} else {{ setTimeout(poll, 4000); }} }});
    }})();
  }}
  // Второй шаг: только после того, как документы скачаны и прочитаны.
  function stepFill(then) {{
    if (!bFill) {{ if (then) then(); return; }}
    if (bScan && bScan.dataset.done !== '1') {{
      scanNote('сначала нужен разбор документов — заполнять пока нечем', true);
      return;
    }}
    stepRun(bFill, '/applications/' + APP_ID + '/autofill-all', 'Поля заполнены', function () {{
      // значения изменились — показываю экран заново с новыми данными
      setTimeout(function () {{ location.reload(); }}, 700);
      if (then) then();
    }});
  }}

  if (bScan) bScan.addEventListener('click', function () {{ stepScan(function () {{ stepFill(); }}, true); }});
  if (bFill) bFill.addEventListener('click', function () {{ stepFill(); }});

  // Смена типа продукта: заявка пересобирается под новый пакет документов,
  // затем оба этапа проходят заново — администратор видит это по значкам.
  // Свой список продуктов: нажатие на строку меняет тип продукта заявки
  var bProduct = document.getElementById('rv-product-btn');
  var bProductList = document.getElementById('rv-product-list');
  var bProductBox = document.getElementById('rv-product');
  if (bProduct && bProductList) {{
    bProduct.addEventListener('click', function (e) {{
      e.stopPropagation();
      bProductList.hidden = !bProductList.hidden;
    }});
    document.addEventListener('click', function (e) {{
      if (!bProductBox.contains(e.target)) bProductList.hidden = true;
    }});
    document.addEventListener('keydown', function (e) {{
      if (e.key === 'Escape') bProductList.hidden = true;
    }});
    Array.from(bProductList.querySelectorAll('.rv-opt')).forEach(function (opt) {{
      opt.addEventListener('click', function () {{
        bProductList.hidden = true;
        if (opt.dataset.value === bProductBox.dataset.value) return;
        setProduct(opt.dataset.value, opt.querySelector('.rv-opt-name').textContent);
      }});
    }});
  }}

  function setProduct(pid, name) {{
    var fd = new FormData();
    fd.append('product_id', pid);
    var bProductSw = document.getElementById('rv-product');
    if (bProductSw) bProductSw.dataset.value = pid;
    if (bScan) {{ bScan.dataset.done = '0'; }}
    if (bFill) {{ bFill.dataset.done = '0'; }}
    valueNote('Меняю тип продукта: подбираю документы и переменные…', 'work');
    fetch('/applications/' + APP_ID + '/review/product',
          {{method: 'POST', body: fd, credentials: 'same-origin',
            headers: {{'X-Requested-With': 'fetch'}}}})
      .then(function (r) {{ return r.json().catch(function () {{ return {{}}; }}); }})
      .then(function (d) {{
        if (!d || !d.ok) {{
          valueNote('⚠ ' + ((d && d.error) || 'не удалось сменить продукт'), 'err');
          return;
        }}
        var cur = document.getElementById('rv-product-cur');
        if (cur) cur.textContent = d.product || name || cur.textContent;
        // подсветка внутри списка переезжает на выбранный продукт
        Array.from(document.querySelectorAll('#rv-product-list .rv-opt')).forEach(function (o) {{
          var onReq = o.dataset.value === String(window.RV_REQ_PID || pid);
          var cur = o.querySelector('.rv-opt-tag.is-cur');
          if (cur) cur.remove();
          o.classList.toggle('is-current', onReq);
          o.classList.toggle('is-picked', !onReq && o.dataset.value === pid);
          if (!onReq && o.dataset.value === pid) {{
            var t = document.createElement('span');
            t.className = 'rv-opt-tag is-cur';
            t.textContent = 'стоит сейчас';
            o.appendChild(t);
          }}
        }});
        valueNote('Продукт сменён: ' + (d.product || '') + ' — обновляю документы и переменные…', 'ok');
        // Под новый продукт приходит свой пакет документов (миниатюры) и свой набор
        // переменных. Перерисовываем страницу, иначе на экране остаётся прежний набор.
        setTimeout(function () {{ window.location.reload(); }}, 400);
      }})
      .catch(function () {{
        valueNote('⚠ не удалось сменить продукт', 'err');
      }});
  }}

  // Автоматический разбор документов при ОТКРЫТИИ заявки убран сознательно:
  // разбор идёт на Google Диск и читает сканы через OCR — если запускать его в
  // момент открытия, страница «зависает» у администратора. Всё это готовится
  // заранее в фоне (scripts/app_prepare.py, с низким приоритетом) и запускается
  // вручную кнопками этапов 1 и 3.
  (function autoSteps() {{
    if (!bScan && !bFill) return;
    return;
  }})();

  if (modal) {{
    modal.addEventListener('click', function(e) {{
      // клик по затемнению вне окна закрывает просмотр
      if (e.target === modal) closeModal();
    }});
  }}
  var mClose = document.getElementById('rv-modal-close');
  if (mClose) mClose.addEventListener('click', closeModal);
  document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') closeModal(); }});

  var loadedOnce = false;
  tabs.forEach(function(t) {{
    t.addEventListener('click', function() {{
      if (t.dataset.pane === 'ready' && !loadedOnce) {{ loadedOnce = true; openDoc(PICKED); }}
    }});
  }});


  // согласование: ✓ проверен / ✕ не нужен
  function verdict(tpl, kind, btn) {{
    if (btn) btn.disabled = true;
    /* Метка ставится сразу, сервер подтверждает состояние в базе. */
    var wasOnBtn = btn ? btn.classList.contains('is-on') : false;
    paintMiniRail(tpl, wasOnBtn ? '' : (kind === 'verify' ? 'verified' : 'rejected'));
    fetch('/applications/' + APP_ID + '/doc/' + tpl + '/' + kind, {{
      method: 'POST', credentials: 'same-origin', keepalive: true, headers: {{'X-Requested-With': 'fetch'}}
    }})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (btn) btn.disabled = false;
        // Сервер отказывает, если документ заполнен не полностью: показываем причину рядом с миниатюрой.
        if (d && d.ok === false && d.error) {{
          // Не заполнены поля: фиксируем документ как есть — галочка встаёт
          // с первого нажатия, без лишнего диалога.
          if (d.can_force && kind === 'verify') {{
            fetch('/applications/' + APP_ID + '/doc/' + tpl + '/verify?force=1', {{
              method: 'POST', credentials: 'same-origin', keepalive: true,
              headers: {{'X-Requested-With': 'fetch'}}
            }})
              .then(function(r) {{ return r.json(); }})
              .then(function() {{ if (btn) btn.disabled = false; refreshStatuses(); refreshState(); }})
              .catch(function() {{ if (btn) btn.disabled = false; }});
            return;
          }}
          var lbl = document.getElementById('rv-thumb-status-' + tpl);
          if (lbl) {{
            if (!lbl.dataset.prev) lbl.dataset.prev = lbl.textContent;
            lbl.textContent = d.error;
            lbl.classList.add('rv-warn');
            setTimeout(function() {{
              if (lbl.dataset.prev) lbl.textContent = lbl.dataset.prev;
              lbl.classList.remove('rv-warn');
            }}, 6000);
          }}
          if (btn) btn.classList.remove('rv-on-ok');
          return;
        }}
        refreshStatuses();
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
  // На телефоне панель переменных открывается кнопкой из шапки заявки
  var bVars = document.getElementById('rv-vars-btn');
  if (bVars) bVars.addEventListener('click', function () {{
    var panel = document.getElementById('rv-right') || document.querySelector('.rv-right');
    if (panel) panel.classList.add('is-open');
  }});

  var mVars = document.getElementById('rv-modal-vars');
  if (mVars) mVars.addEventListener('click', function() {{
    var panel = document.getElementById('rv-right') || document.querySelector('.rv-right');
    if (!panel) return;
    panel.classList.add('is-open');
  }});

  if (mOk) mOk.addEventListener('click', function() {{ modalVerdict('verify'); }});
  if (mNo) mNo.addEventListener('click', function() {{ modalVerdict('reject'); }});

  // Квадратик-подтверждение. Клик по нему НЕ выбирает документ (stopPropagation).
  Array.from(document.querySelectorAll('.rv-mark')).forEach(function(b) {{
    b.addEventListener('click', function(e) {{
      e.stopPropagation();
      verdict(b.dataset.tpl, b.dataset.verdict, b);
    }});
  }});
  // Сканы с Диска: квадратик означает «скачано с Диска», подпись меняется сразу.
  function driveStamp() {{
    var d = new Date();
    return ('0' + d.getDate()).slice(-2) + '.' + ('0' + (d.getMonth() + 1)).slice(-2);
  }}
  Array.from(document.querySelectorAll('.rv-check[data-check="drive"]')).forEach(function(b) {{
    b.addEventListener('click', function(e) {{
      e.stopPropagation();
      var tile = b.closest('.rv-thumb');
      if (!tile) return;
      var on = tile.classList.toggle('is-checked');
      b.classList.toggle('rv-on-ok', on);
      var st = tile.querySelector('.rv-thumb-state');
      if (st) st.textContent = on ? ('Скачано с Диска · ' + driveStamp()) : 'не подтверждено';
    }});
  }});

  // Метка на миниатюре — отражение нажатой кнопки: крестик или галочка по центру
  // листа. Состояние берём с сервера, поэтому метка появляется и снимается сразу
  // после нажатия, без перезагрузки страницы.
  function paintTile(tpl, state) {{
    var tile = document.querySelector('.rv-thumb[data-tpl="' + tpl + '"]');
    if (!tile) return;
    var off = state === 'rejected';
    var ok = state === 'verified' || state === 'sent';
    tile.classList.toggle('is-off', off);
    tile.classList.toggle('is-ok', ok);
    var st = tile.querySelector('.rv-thumb-status');
    if (st) {{
      st.classList.toggle('is-off', off);
      st.classList.toggle('is-ok', ok);
    }}
    var mk = tile.querySelector('.rv-thumb-mark');
    if (mk) mk.title = off ? 'Отклонён: документ не нужен в этой заявке'
                           : (ok ? 'Проверен и зафиксирован для отправки' : '');
    var why = tile.querySelector('.rv-thumb-why');
    if (why) why.style.display = off ? '' : 'none';
  }}

  // Метка на миниатюре конструктора (столбик документов) — то же отражение
  // нажатой кнопки: ✕ или ✓ по центру листа. Исключённые скатываются вниз.
  function paintMiniRail(tpl, state) {{
    var off = state === 'rejected', ok = (state === 'verified' || state === 'sent');
    document.querySelectorAll('.tpl-mini[data-tpl="' + tpl + '"]').forEach(function(tile) {{
      tile.classList.toggle('is-off', off);
      tile.classList.toggle('is-ok', ok);
      var host = tile.querySelector('.tpl-mini-name') || null;
      var x = tile.querySelector('.tpl-mini-x');
      var m = tile.querySelector('.tpl-mini-ok');
      if (off && !x) {{ x = document.createElement('span'); x.className = 'tpl-mini-x'; x.textContent = '✕'; tile.insertBefore(x, host); }}
      if (!off && x) x.remove();
      if (ok && !m) {{ m = document.createElement('span'); m.className = 'tpl-mini-ok'; m.textContent = '✓'; tile.insertBefore(m, host); }}
      if (!ok && m) m.remove();
    }});
    var body = document.getElementById('tpl-rail-body');
    if (!body) return;
    var tiles = Array.prototype.slice.call(body.querySelectorAll('.tpl-mini-wrap'));
    if (tiles.length < 2) return;
    var key = function(t) {{
      var inner = t.querySelector('.tpl-mini') || t;
      var n = t.querySelector('.tpl-mini-num');
      var mm = (n ? (n.textContent || '') : '').match(/\\d+/);
      return [(inner.classList.contains('is-off') ? 1 : 0), mm ? parseInt(mm[0], 10) : 999];
    }};
    tiles.sort(function(a, b) {{ var ka = key(a), kb = key(b); return (ka[0] - kb[0]) || (ka[1] - kb[1]); }});
    tiles.forEach(function(t) {{ body.appendChild(t); }});
  }}

  // состояние документов: обновляет подписи и кнопки на плитках и в окне
  function refreshStatuses() {{
    fetch('/applications/' + APP_ID + '/review/statuses', {{credentials: 'same-origin'}})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (!d || !d.ok) return;
        Object.keys(d.statuses || {{}}).forEach(function(tpl) {{
          var state = d.statuses[tpl] || '';
          paintTile(tpl, state);
          paintMiniRail(tpl, state);
          var lbl = document.getElementById('rv-thumb-status-' + tpl);
          if (lbl) lbl.textContent = state === 'rejected' ? 'не нужен'
                                  : state === 'verified' ? 'проверен · в очереди на отгрузку'
                                  : state === 'rendered' ? 'собран · не проверено'
                                  : state === 'filled' ? 'заполнен · не проверено'
                                  : state === 'draft' ? 'черновик · ждём скан'
                                  : 'не проверено';
          Array.from(document.querySelectorAll('.rv-mark[data-tpl="' + tpl + '"]')).forEach(function(x) {{
            var isOk = x.dataset.verdict === 'verify';
            var on = (isOk && state === 'verified') || (!isOk && state === 'rejected');
            x.classList.toggle(isOk ? 'rv-on-ok' : 'rv-on-no', on);
            /* те же кнопки в окне визора, на миниатюрах и в просмотре PDF подсвечиваются так же */
            x.classList.toggle('is-on', on);
          }});
          if (String(tpl) === String(modalTpl)) {{
            if (mOk) mOk.classList.toggle('is-on', state === 'verified');
            if (mNo) mNo.classList.toggle('is-on', state === 'rejected');
          }}
        }});
      }})
      .catch(function() {{}});
  }}

  /* Обновление подписей и подвала заявки «снаружи» (из конструктора окна визора) */
  window.__rvRefresh = function () {{ refreshStatuses(); refreshState(); }};

  // готовность комплекта без перезагрузки
  function refreshState() {{
    fetch('/applications/' + APP_ID + '/send-state', {{credentials: 'same-origin'}})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (!d || !d.ok) return;
        var st = document.querySelector('.rv-state');
        if (st) {{
          st.className = 'rv-state ' + (d.can_send ? 'ok' : 'warn');
          st.textContent = d.can_send
            ? '✅ Все документы согласованы — можно отправлять'
            : '⛔ Отправить нельзя: согласовано ' + d.ready + ' из ' + d.total + ' документов';
        }}
        var btn = document.querySelector('.rv-send button');
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
  function valueNote(text, tone) {{
    var el = document.getElementById('rv-value-note');
    if (!el) return;
    var colors = {{ok: '#14663A', warn: '#8A5A00', err: '#B91C1C', work: '#5B6B62'}};
    el.style.color = colors[tone] || colors.work;
    el.textContent = text;
  }}
  function inputByKey(key) {{
    var found = null;
    Array.from(document.querySelectorAll('.rv-input')).forEach(function(x) {{
      if (x.dataset.key === key) found = x;
    }});
    return found;
  }}
  function refreshViewer() {{
    // Если документ открыт в окне просмотра — показываем его заново с новыми
    // значениями. Миниатюры тоже обновляем: они отражают тот же документ.
    if (modalTpl) loadInto(modalTpl);
    else if (modal && modal.classList.contains('is-on') && !modalTpl) return;
    else {{
      Array.from(document.querySelectorAll('#rv-thumbs .rv-thumb iframe')).forEach(function(fr) {{
        var src = fr.dataset.src || fr.getAttribute('src');
        if (src) {{
          fr.setAttribute('src', 'about:blank');
          setTimeout(function() {{ fr.setAttribute('src', src); }}, 60);
        }}
      }});
    }}
  }}
  function sendValue(act, key, value, btn) {{
    var url = '/applications/' + APP_ID + '/review/' + (act === 'regen' ? 'regen' : 'value');
    var body = new URLSearchParams();
    body.set('key', key);
    if (value !== null && value !== undefined) body.set('value', value);
    if (btn) btn.disabled = true;
    fetch(url, {{method: 'POST', credentials: 'same-origin', body: body,
                headers: {{'X-Requested-With': 'fetch'}}}})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (btn) btn.disabled = false;
        if (!d.ok) {{ valueNote('⚠ ' + (d.error || 'не получилось'), 'err'); return; }}
        var inp = inputByKey(key);
        if (inp && d.value !== undefined) {{
          inp.value = d.value;
          inp.classList.remove('is-empty');
          inp.classList.add('is-saved');
          setTimeout(function() {{ inp.classList.remove('is-saved'); }}, 1200);
        }}
        var docs = (d.touched && d.touched.length) ? d.touched.length : (d.doc_count || 0);
        valueNote((act === 'regen' ? '↻ перегенерировано: ' : '💾 сохранено: ')
                  + (d.label || 'поле')
                  + (docs ? ' · обновлено документов: ' + docs : ''), 'ok');
        refreshViewer();
      }})
      .catch(function() {{ if (btn) btn.disabled = false; valueNote('⚠ ошибка сети', 'err'); }});
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
    fetch('/applications/' + APP_ID + '/review/options?key=' + encodeURIComponent(key),
          {{credentials: 'same-origin'}})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (!d.options || !d.options.length) {{
          valueNote('прошлых значений для этого поля пока нет', 'warn');
          return;
        }}
        var box = document.createElement('div');
        box.className = 'rv-optlist';
        d.options.forEach(function(v) {{
          var b = document.createElement('button');
          b.type = 'button';
          b.textContent = v;
          b.addEventListener('click', function(e) {{
            e.stopPropagation();
            var inp = field.querySelector('.rv-input');
            if (inp) {{
              inp.value = v;
              inp.defaultValue = v;
            }}
            hideOptions();
            sendValue('value', key, v, null);
          }});
          box.appendChild(b);
        }});
        field.appendChild(box);
      }})
      .catch(function() {{ valueNote('⚠ не удалось получить список', 'err'); }});
  }}
  // Расхождение документа и анкеты: администратор выбирает, какое значение
  // подставить. Выбор запоминается и разбором документов больше не перебивается.
  Array.from(document.querySelectorAll('.rv-conflict-sel')).forEach(function (sel) {{
    sel.addEventListener('change', function () {{
      var key = sel.getAttribute('data-key');
      var opt = sel.options[sel.selectedIndex];
      var val = (opt && opt.getAttribute('data-value')) || '';
      var src = sel.value;                       // 'doc' — из документа, 'card' — из анкеты
      var field = sel.closest('.rv-field');
      var inp = field ? field.querySelector('.rv-input') : null;
      if (inp) {{ inp.value = val; inp.defaultValue = val; }}
      var body = new URLSearchParams();
      body.set('key', key);
      body.set('value', val);
      body.set('source', src);
      fetch('/applications/' + APP_ID + '/review/value',
            {{method: 'POST', credentials: 'same-origin', body: body,
              headers: {{'X-Requested-With': 'fetch'}}}})
        .then(function (r) {{ return r.json(); }})
        .then(function (d) {{
          if (!d || !d.ok) {{ valueNote('⚠ не сохранилось', 'err'); return; }}
          if (field) field.classList.remove('is-conflict');
          var head = field ? field.querySelector('.rv-conflict-head') : null;
          if (head) {{
            head.textContent = (src === 'doc') ? '✓ значение взято из документа'
                                               : '✓ значение взято из анкеты';
            head.style.color = '#15803D';
          }}
          valueNote('✅ Значение обновлено' + (d.docs_updated ? ' · документов: ' + d.docs_updated : ''), 'ok');
        }})
        .catch(function () {{ valueNote('⚠ не сохранилось', 'err'); }});
    }});
  }});

  // Кнопка осталась одна — «сгенерировать заново». Сохранение отдельной кнопкой
  // больше не нужно: значение записывается само, а список прошлых значений
  // открывается прямо по нажатию на поле.
  // Список прошлых значений закрывается, когда нажимаешь в любое другое место
  // или жмёшь Esc, — иначе он перекрывал поля и мешал работать.
  document.addEventListener('click', function (e) {{
    var inList = e.target.closest && e.target.closest('.rv-optlist');
    var inField = e.target.closest && e.target.closest('.rv-input, .rv-act');
    if (!inList && !inField) hideOptions();
  }}, true);
  document.addEventListener('keydown', function (e) {{
    if (e.key === 'Escape') hideOptions();
  }});
  window.addEventListener('blur', hideOptions);

  Array.from(document.querySelectorAll('.rv-act')).forEach(function(b) {{
    b.addEventListener('click', function() {{
      if (b.dataset.act === 'regen') sendValue('regen', b.dataset.key, null, b);
    }});
  }});
  Array.from(document.querySelectorAll('.rv-input')).forEach(function(inp) {{
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
    inp.addEventListener('change', function() {{ saveField(inp); }});
  }});
  // сохраняем только если значение действительно поменялось — иначе лишние пересборки
  function saveField(inp) {{
    if (!inp) return;
    if (inp.value === inp.defaultValue) {{ valueNote('значение не изменилось', 'work'); return; }}
    inp.defaultValue = inp.value;
    sendValue('value', inp.dataset.key, inp.value, null);
  }}
  function hideOptions() {{
    Array.from(document.querySelectorAll('.rv-optlist')).forEach(function(b) {{ b.remove(); }});
  }}


  // ── миниатюры документов: подгружаются лениво, прогресс виден ──
  var thumbLoaded = false;
  function loadThumbs() {{
    var list = Array.from(document.querySelectorAll('#rv-thumbs .rv-thumb'));
    if (!list.length) return;
    var done = 0;
    var counter = document.getElementById('rv-thumbs-count');
    function tick() {{
      done++;
      if (counter) counter.textContent = 'миниатюры готовы: ' + done + ' из ' + list.length;
    }}
    list.forEach(function(t) {{
      var frame = t.querySelector('.rv-thumb-frame');
      // Миниатюра плитки — картинка (WebP); полный документ открывается в окне.
      var fr = t.querySelector('img, iframe');
      if (!fr || !fr.dataset.src) {{ tick(); return; }}
      frame.classList.add('is-loading');
      fr.addEventListener('load', function() {{
        frame.classList.remove('is-loading');
        frame.classList.add('is-ready');
        tick();
      }});
      fr.setAttribute('src', fr.dataset.src);
    }});
  }}
  Array.from(document.querySelectorAll('#rv-thumbs .rv-thumb')).forEach(function(t) {{
    t.addEventListener('click', function(e) {{
      if (e.target.closest('.rv-thumb-tools')) return;   // кнопки согласования не открывают окно
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
    el.classList.add('var-flash');
    setTimeout(function() {{ el.classList.remove('var-flash'); }}, ms || 2600);
  }}
  function fieldFor(varName) {{
    var found = null;
    Array.from(document.querySelectorAll('.rv-field')).forEach(function(f) {{
      var vars = (f.dataset.vars || '').split(',');
      if (vars.indexOf(varName) >= 0) found = f;
    }});
    return found;
  }}
  function activeHost() {{
    // На экране два окна просмотра: входящий файл и готовый документ.
    // Подсвечивать нужно в том, которое администратор сейчас видит.
    var hosts = Array.from(document.querySelectorAll('[data-zoom-pan]'));
    for (var i = 0; i < hosts.length; i++) {{
      if (hosts[i].offsetParent !== null) return hosts[i];
    }}
    return hosts[0] || null;
  }}
  // клик по полю справа → подсветить это место в документе слева
  Array.from(document.querySelectorAll('.rv-field')).forEach(function(f) {{
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
      document.querySelectorAll('.rv-field.var-active').forEach(function(x) {{ x.classList.remove('var-active'); }});
      f.classList.add('var-active');
      setTimeout(function() {{ f.classList.remove('var-active'); }}, 2600);
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
          var p = document.getElementById('rv-right');
          var bd = document.getElementById('rv-backdrop');
          if (p) p.classList.add('is-open');
          if (bd) bd.classList.add('is-on');
        }}
        Array.from(document.querySelectorAll('.rv-field.var-active')).forEach(function(y) {{
          y.classList.remove('var-active');
        }});
        f.classList.add('var-active');
        f.scrollIntoView({{block: 'center', behavior: 'smooth'}});
        flashEl(f);
      }});
    }});
  }}

  // ── на телефоне панель переменных выезжает по кнопке снизу ──
  function openRight() {{
    var p = document.getElementById('rv-right');
    var bd = document.getElementById('rv-backdrop');
    if (p) p.classList.add('is-open');
    if (bd) bd.classList.add('is-on');
  }}
  function closeRight() {{
    var p = document.getElementById('rv-right');
    var bd = document.getElementById('rv-backdrop');
    if (p) p.classList.remove('is-open');
    if (bd) bd.classList.remove('is-on');
  }}
  var mbar = document.getElementById('rv-mobile-bar');
  if (mbar) mbar.addEventListener('click', openRight);
  var rclose = document.getElementById('rv-right-close');
  if (rclose) rclose.addEventListener('click', closeRight);
  var bdEl = document.getElementById('rv-backdrop');
  if (bdEl) bdEl.addEventListener('click', closeRight);

  // ── входящие файлы: клик открывает документ поверх страницы ──
  Array.from(document.querySelectorAll('.rv-file-thumb')).forEach(function(t) {{
    t.addEventListener('click', function() {{ openFile(t); }});
  }});

}})();

  // Резюме: выбор профессии и сборка описания прямо в карточке заявки.
  (function () {{
    var sels = Array.prototype.slice.call(document.querySelectorAll('.rv-cvprof'));
    if (!sels.length) return;
    var parts = location.pathname.split('/');
    var ai = parts.indexOf('applications');
    var appId = ai >= 0 ? (parts[ai + 1] || '') : '';
    if (!appId) return;
    fetch('/applications/' + appId + '/review/professions',
          {{headers: {{'X-Requested-With': 'fetch'}}}})
      .then(function (r) {{ return r.json(); }})
      .then(function (d) {{
        (d.items || []).forEach(function (it) {{
          sels.forEach(function (sel) {{
            var o = document.createElement('option');
            o.value = it.code;
            o.textContent = it.ru || it.en || it.code;
            sel.appendChild(o);
          }});
        }});
      }})
      .catch(function () {{}});

    Array.prototype.slice.call(document.querySelectorAll('.rv-cvbtn')).forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        var key = btn.dataset.key;
        var sel = document.querySelector('.rv-cvprof[data-key="' + key + '"]');
        var prof = sel ? sel.value : '';
        var was = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Собираю…';
        var fd = new FormData();
        fd.append('key', key);
        if (prof) fd.append('profession', prof);
        fetch('/applications/' + appId + '/review/regen',
              {{method: 'POST', body: fd, headers: {{'X-Requested-With': 'fetch'}}}})
          .then(function (r) {{ return r.json(); }})
          .then(function (d) {{
            btn.disabled = false;
            btn.textContent = was;
            if (d && d.ok && typeof d.value === 'string') {{
              var ta = document.querySelector('.rv-input[data-key="' + key + '"]');
              if (ta) {{
                ta.value = d.value;
                ta.style.height = 'auto';
                ta.style.height = (ta.scrollHeight + 2) + 'px';
                ta.classList.remove('is-empty');
              }}
            }}
          }})
          .catch(function () {{ btn.disabled = false; btn.textContent = was; }});
      }});
    }});
  }})();

  // ── Резюме: кусочки, сборка с нуля, своя профессия ─────────────────────────
  (function () {{
    var parts = location.pathname.split('/');
    var ai = parts.indexOf('applications');
    var APP = ai >= 0 ? (parts[ai + 1] || '') : '';
    if (!APP) return;
    var box = null;

    function inp(key) {{ return document.querySelector('.rv-input[data-key="' + key + '"]'); }}
    function profOf(key) {{
      var s = document.querySelector('.rv-cvprof[data-key="' + key + '"]');
      return (s && s.value && s.value !== '__custom__') ? s.value : '';
    }}
    function save(key, value) {{
      var fd = new FormData();
      fd.append('key', key);
      fd.append('value', value);
      return fetch('/applications/' + APP + '/review/value',
                   {{method: 'POST', body: fd, headers: {{'X-Requested-With': 'fetch'}}}});
    }}
    function put(key, value) {{
      var ta = inp(key);
      if (!ta) return;
      ta.value = value;
      ta.style.height = 'auto';
      ta.style.height = (ta.scrollHeight + 2) + 'px';
    }}
    function closeBox() {{ if (box) {{ box.remove(); box = null; }} }}
    function esc(s) {{ return String(s).replace(/</g, '&lt;'); }}

    function openPieces(key, pairs) {{
      closeBox();
      box = document.createElement('div');
      box.className = 'rv-piece-modal';
      var rows = pairs.map(function (p, i) {{
        var ru = esc((p && (p.ru || p.en)) || p);
        var en = esc((p && p.en) || p);
        return '<label class="rv-piece-row"><input type="checkbox" value="' + i + '">' +
               '<span>' + ru + (en && en !== ru ? '<span class="rv-piece-en">' + en + '</span>' : '') +
               '</span></label>';
      }}).join('');
      box.innerHTML = '<div class="rv-piece-box"><div class="rv-piece-head">' +
        'Готовые фразы — отметьте нужные</div><div class="rv-piece-list">' +
        (rows || '<div class="rv-piece-row">Готовых фраз пока нет — нажмите «С нуля»</div>') +
        '</div><div class="rv-piece-foot"><button type="button" class="rv-piece-cancel">Отмена</button>' +
        '<button type="button" class="rv-piece-ok">Подставить выбранные</button></div></div>';
      document.body.appendChild(box);
      box.querySelector('.rv-piece-cancel').addEventListener('click', closeBox);
      box.addEventListener('click', function (e) {{ if (e.target === box) closeBox(); }});
      box.querySelector('.rv-piece-ok').addEventListener('click', function () {{
        var picked = Array.prototype.slice.call(box.querySelectorAll('input:checked'))
          .map(function (c) {{ var p = pairs[parseInt(c.value, 10)]; return (p && p.en) || p; }});
        if (!picked.length) {{ closeBox(); return; }}
        // описание профессии — связный абзац без маркеров; обязанности — пунктами
        var isProse = /summary|profile|описан/i.test(key);
        var text = isProse
          ? picked.map(function (s) {{ return String(s).replace(/^[\u2022\-\s]+/, '').trim(); }}).join(' ')
          : picked.join('\\n');
        if (isProse && text && !/[.!?]$/.test(text)) {{ text += '.'; }}
        put(key, text);
        save(key, text).then(closeBox);
      }});
    }}

    Array.prototype.slice.call(document.querySelectorAll('.rv-cvpieces')).forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        var key = btn.dataset.key;
        var url = '/applications/' + APP + '/review/phrases?key=' + encodeURIComponent(key) +
                  '&profession=' + encodeURIComponent(profOf(key));
        fetch(url, {{headers: {{'X-Requested-With': 'fetch'}}}})
          .then(function (r) {{ return r.json(); }})
          .then(function (d) {{
            var pairs = (d && d.pairs) || [];
            if (!pairs.length) {{
              pairs = ((d && d.items) || []).map(function (s) {{ return {{ en: s, ru: s }}; }});
            }}
            openPieces(key, pairs);
          }})
          .catch(function () {{ openPieces(key, []); }});
      }});
    }});

    Array.prototype.slice.call(document.querySelectorAll('.rv-cvscratch')).forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        var key = btn.dataset.key;
        var was = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Собираю…';
        var fd = new FormData();
        fd.append('key', key);
        fd.append('profession', profOf(key));
        fetch('/applications/' + APP + '/review/scratch',
              {{method: 'POST', body: fd, headers: {{'X-Requested-With': 'fetch'}}}})
          .then(function (r) {{ return r.json(); }})
          .then(function (d) {{
            btn.disabled = false;
            btn.textContent = was;
            if (d && d.ok && typeof d.value === 'string') {{ put(key, d.value); }}
            else if (d && d.error) {{ alert(d.error); }}
          }})
          .catch(function () {{ btn.disabled = false; btn.textContent = was; }});
      }});
    }});

    Array.prototype.slice.call(document.querySelectorAll('.rv-cvprof')).forEach(function (sel) {{
      sel.addEventListener('change', function () {{
        if (sel.value !== '__custom__') return;
        var title = window.prompt('Название профессии');
        if (!title) {{ sel.value = ''; return; }}
        var fd = new FormData();
        fd.append('title', title);
        fetch('/applications/' + APP + '/review/profession_add',
              {{method: 'POST', body: fd, headers: {{'X-Requested-With': 'fetch'}}}})
          .then(function (r) {{ return r.json(); }})
          .then(function (d) {{
            if (!d || !d.ok) {{ sel.value = ''; alert((d && d.error) || 'не получилось'); return; }}
            var o = document.createElement('option');
            o.value = d.code;
            o.textContent = d.title;
            var custom = sel.querySelector('option[value="__custom__"]');
            sel.insertBefore(o, custom);
            sel.value = d.code;
          }})
          .catch(function () {{ sel.value = ''; }});
      }});
    }});
  }})();

  // ── Организация для договора: выбор из пула исторических документов ────────
  (function () {{
    var parts = location.pathname.split('/');
    var ai = parts.indexOf('applications');
    var APP = ai >= 0 ? (parts[ai + 1] || '') : '';
    if (!APP) return;
    // связанные переменные: название в шапке, название в тексте, адрес и реквизиты в подвале
    var RELATED = ['company_name_in_quotes', 'employer_name', 'company_registered_address',
                   'company_inn', 'company_kpp', 'company_ogrn'];

    function inp(key) {{ return document.querySelector('.rv-input[data-key="' + key + '"]'); }}
    function put(key, value) {{
      var ta = inp(key);
      if (!ta) return;
      ta.value = value;
      ta.style.height = 'auto';
      ta.style.height = (ta.scrollHeight + 2) + 'px';
    }}
    function save(key, value) {{
      var fd = new FormData();
      fd.append('key', key);
      fd.append('value', value);
      return fetch('/applications/' + APP + '/review/value',
                   {{method: 'POST', body: fd, headers: {{'X-Requested-With': 'fetch'}}}});
    }}
    function rebuild() {{
      return fetch('/applications/' + APP + '/review/rebuild',
                   {{method: 'POST', headers: {{'X-Requested-With': 'fetch'}}}});
    }}

    Array.prototype.slice.call(document.querySelectorAll('.rv-empsel')).forEach(function (sel) {{
      sel.addEventListener('change', function () {{
        if (sel.value === '') return;
        fetch('/applications/' + APP + '/review/employer_values?index=' + encodeURIComponent(sel.value),
              {{headers: {{'X-Requested-With': 'fetch'}}}})
          .then(function (r) {{ return r.json(); }})
          .then(function (d) {{
            if (!d || !d.ok) {{ alert((d && d.error) || 'организация не найдена'); return; }}
            RELATED.forEach(function (k) {{
              var v = (d.values && d.values[k]) || '';
              put(k, v);
              save(k, v);
            }});
            rebuild().catch(function () {{}});
          }})
          .catch(function () {{ alert('не получилось применить организацию'); }});
      }});
    }});
  }})();
"""
