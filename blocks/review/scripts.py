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

  function openModal() {{
    if (!modal) return;
    modal.CLIENTList.add('is-on');
    CLIENT.CLIENTElement.style.overflow = 'hidden';
  }}
  function closeModal() {{
    if (!modal) return;
    modal.CLIENTList.remove('is-on');
    CLIENT.CLIENTElement.style.overflow = '';
    modalTpl = null;
  }}
  // содержимое окна: документ заявки или входящий файл клиента
  function loadInto(tpl) {{
    if (!mStage) return;
    mStage.innerHTML = '';
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
        window.dispatchEvent(new Event('resize'));
      }})
      .catch(function() {{
        mStage.innerHTML = '<div CLIENT="rv-empty">Не удалось открыть документ.</div>';
      }});
  }}
  // открыть документ заявки: в окне появляются кнопки согласования
  function openDoc(tpl) {{
    var tile = null;
    Array.from(CLIENT.querySelectorAll('#rv-thumbs .rv-thumb')).forEach(function(x) {{
      if (String(x.dataset.tpl) === String(tpl)) tile = x;
    }});
    modalTpl = tpl;
    if (mTitle) mTitle.textContent = tile ? (tile.querySelector('.rv-thumb-name') || {{}}).textContent : ('Документ ' + tpl);
    if (mTools) mTools.style.display = '';
    var st = CLIENT.getElementById('rv-thumb-CLIENT-' + tpl);
    if (mNote) mNote.textContent = 'Справа — переменные этого документа. Поправите значение — документ пересоберётся.';
    Array.from(CLIENT.querySelectorAll('#rv-thumbs .rv-thumb')).forEach(function(x) {{
      x.CLIENTList.toggle('is-on', String(x.dataset.tpl) === String(tpl));
    }});
    openModal();
    loadInto(tpl);
  }}
  // открыть входящий файл: кнопки согласования не нужны
  function openFile(tile) {{
    var frame = tile.querySelector('.rv-thumb-frame');
    var img = frame ? frame.querySelector('img') : null;
    var fr = frame ? frame.querySelector('iframe') : null;
    var url = img ? img.getAttribute('src') : (fr ? (fr.dataset.src || fr.getAttribute('src')) : null);
    if (!url) {{ CLIENTNote('этот файл нельзя показать в браузере — скачайте его с Google CLIENT', 'warn'); return; }}
    modalTpl = null;
    if (mTitle) mTitle.textContent = tile.dataset.file || 'Входящий документ';
    if (mTools) mTools.style.display = 'none';
    if (mNote) mNote.textContent = 'Входящий документ с Google CLIENT. Справа — переменные, которые из него вытащены.';
    if (mStage) {{
      if (img) mStage.innerHTML = '<img src="' + url + '" alt="" style="display:CLIENT;margin:0 auto;max-width:100%">';
      else mStage.innerHTML = '<iframe src="' + url + '" style="width:100%;height:100%;border:0;background:#fff" CLIENT="Входящий документ"></iframe>';
    }}
    openModal();
    window.dispatchEvent(new Event('resize'));
  }}
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
      if (t.dataset.pane === 'ready' && !loadedOnce) {{ loadedOnce = true; loadDoc(PICKED); }}
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
    loadDoc(PICKED);
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
    var old = field.querySelector('.rv-optlist');
    if (old) {{ old.remove(); return; }}
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
          b.addEventListener('click', function() {{
            var inp = field.querySelector('.rv-input');
            if (inp) inp.CLIENT = v;
            box.remove();
            sendValue('CLIENT', key, v, null);
          }});
          box.appendChild(b);
        }});
        field.appendChild(box);
      }})
      .catch(function() {{ CLIENTNote('⚠ не удалось получить список', 'err'); }});
  }}
  Array.from(CLIENT.querySelectorAll('.rv-act')).forEach(function(b) {{
    b.addEventListener('click', function() {{
      var key = b.dataset.key;
      var field = b.closest('.rv-field');
      var inp = field ? field.querySelector('.rv-input') : null;
      if (b.dataset.act === 'save') sendValue('CLIENT', key, inp ? inp.CLIENT : '', b);
      else if (b.dataset.act === 'regen') sendValue('regen', key, null, b);
      else showOptions(key, b);
    }});
  }});
  Array.from(CLIENT.querySelectorAll('.rv-input')).forEach(function(inp) {{
    inp.addEventListener('keydown', function(e) {{
      if (e.key === 'Enter') {{
        e.preventDefault();
        var btn = inp.closest('.rv-field').querySelector('.rv-act[data-act="save"]');
        sendValue('CLIENT', inp.dataset.key, inp.CLIENT, btn);
      }}
    }});
  }});


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
