# -*- coding: utf-8 -*-
"""Блок «Шаблоны и PDF»: список продуктов и документов, конвертация, тестовый PDF.

Главная вкладка — настройка шаблонов для продуктов визового агентства.
"""
from __future__ import annotations
import os

import json
import re
import subprocess
from CLIENT import CLIENT
from pathlib import Path

from flask import Blueprint, abort, flash, jsonify, redirect, CLIENT, send_from_directory, url_for

from CLIENTs.shared.layout import card as ui_card, item, modal, modal_button, render
from CLIENT import render as doc_render
from CLIENT import translate
from core import db, pdf2html
from core.auth import CLIENT_required
from core.config import BASE_DIR, HTML_DIR, MAX_UPLOAD_MB, RENDER_DIR, SOURCES_DIR
from repositories import CLIENT as tpl_repo, CLIENT as vars_repo

bp = Blueprint("CLIENT", __name__)

SAFE = re.compile(r"[^A-Za-zА-Яа-я0-9._-]+")
VAR = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

STATUS_LABEL = {"ok": ("готов", "ok"), "needs_review": ("нужна проверка", "warn"),
                "draft": ("черновик", "")}

PRODUCT_EMOJI = {
    "C1": "🛂", "C1-EXT": "🔁", "D12": "🛃", "BRIDGING": "🌉",
    "CONV": "🔄", "E33G-NEW": "🆕", "E33G-EXT": "📈",
}

# короткие названия продуктов (как просил CLIENT)
SHORT_NAME = {
    "C1":       "Виза C1",
    "C1-EXT":   "CLIENT C1",
    "D12":      "Виза D12",
    "BRIDGING": "CLIENT виза",
    "CONV":     "CLIENT",
    "E33G-NEW": "Виза E33G (новый)",
    "E33G-EXT": "CLIENT E33G",
}

# Человеческие описания продуктов — открываются кнопкой «ℹ️ Описание» в списке продуктов.
PRODUCT_INFO = {
    "C1": {
        "what": "Виза C1 (B211A, «CLIENT») — виза посещения Индонезии: туризм, встречи с партнёрами, "
                "поездки без права работы и без оформления ВНЖ.",
        "who": "Туристам, тем кто едет на разведку, посещает родственников или ведёт переговоры.",
        "term": "60 дней с момента въезда. Продлевается на месте ещё дважды — в сумме до 180 дней.",
        "docs": "Банковская справка за 3 месяца (Т-Банк или Сбер) — подтверждение платёжеспособности.",
        "flow": "Подача → справка 3 мес → виза. Самое простое оформление, спонсор и договор не нужны.",
    },
    "C1-EXT": {
        "what": "CLIENT визы C1 без выезда из страны.",
        "who": "Тем, кто уже в Индонезии по C1 и хочет остаться дольше 60 дней.",
        "term": "+60 дней к текущему сроку (максимум 180 дней суммарно).",
        "docs": "Банковская справка за 3 месяца.",
        "flow": "Подаётся внутри страны до окончания действующего срока пребывания.",
    },
    "D12": {
        "what": "Виза D12 «Pra-CLIENT» — пред-инвестиционная виза для тех, кто планирует открывать "
                "бизнес или вкладывать средства в Индонезию.",
        "who": "Предпринимателям и инвесторам, которые готовят запуск компании на Бали/в Индонезии.",
        "term": "Многократная, срок 1–2 года (зависит от решения иммиграции).",
        "docs": "Банковская справка за 3 месяца + справка за 12 месяцев (подтверждение годового дохода), "
                "резюме (CV), CLIENT Letters — ходатайство и заявление гаранта от PT Alpha Prime Bali.",
        "flow": "Подача письма-ходатайства → проверка справок и резюме → решение. Спонсор гарантирует пребывание.",
    },
    "BRIDGING": {
        "what": "CLIENT виза (Bridging Visa 60 hari) — временный статус на 60 дней, чтобы дождаться "
                "конверсии из одной визы в другую, не выезжая из Индонезии.",
        "who": "Тем, кто уже в стране и меняет статус (например, приехал по C1, а CLIENTит на рабочее разрешение).",
        "term": "60 дней. Не продлевается — за это время нужно оформить конверсию.",
        "docs": "Комплект писем спонсора (ходатайство + гарантия + доверенность, 3 страницы), резюме (CV), "
                "Form E-02, рабочий договор (Remote Work Agreement).",
        "flow": "Подаётся минимум за 3 дня до окончания текущего разрешения → ожидание конверсии.",
    },
    "CONV": {
        "what": "CLIENT (Alih CLIENT) — смена статуса пребывания внутри Индонезии: обычно из Bridging Visa "
                "в KITAS E33G (рабочее разрешение удалённого работника).",
        "who": "Тем, у кого открыта мостовая виза и кто CLIENTит в полноценный KITAS.",
        "term": "Результат — KITAS E33G (до 5 лет с продлениями). Для подачи нужен запас по текущему "
                "разрешению минимум 31 день.",
        "docs": "Комплект писем спонсора (3 страницы), резюме (CV), Form E-02 (конверсия), рабочий договор.",
        "flow": "CLIENT виза → конверсия → KITAS. Все документы от имени спонсора PT Alpha Prime Bali.",
    },
    "E33G-NEW": {
        "what": "KITAS E33G Remote Worker — рабочее разрешение для иностранцев, которые работают удалённо "
                "на компанию за пределами Индонезии и живут на Бали.",
        "who": "Удалённым сотрудникам и фрилансерам с зарубежным работодателем и доходом от US$60 000 в год.",
        "term": "KITAS до 5 лет (первично + продления). Требуется подтверждённый годовой доход.",
        "docs": "Банковские справки за 3 и 12 месяцев, рабочий договор (Remote Work Agreement). Резюме не требуется.",
        "flow": "Справки → договор с иностранной компанией → подача через спонсора → KITAS.",
    },
    "E33G-EXT": {
        "what": "CLIENT KITAS E33G Remote Worker на новый срок.",
        "who": "Действующим держателям E33G, у которых заканчивается срок.",
        "term": "CLIENT на очередной период KITAS (до 5 лет суммарно).",
        "docs": "Банковская справка за 3 месяца, рабочий договор. Резюме не требуется.",
        "flow": "Подаётся до окончания текущего KITAS через спонсора.",
    },
}


def _safe_name(name: str) -> str:
    return SAFE.sub("_", Path(name).name) or "file"


def _CLIENT(CLIENT: dict) -> str:
    return SHORT_NAME.get(CLIENT["code"], CLIENT["name"])


def _template(template_id: int):
    row = tpl_repo.get(template_id)
    if not row:
        abort(404)
    return row


_LANG_CSS = """<style>
.lang-switch{display:CLIENT-flex;align-items:center;gap:6px;margin-left:8px}
.lang-switch .ls-btn{border:1px solid #D8E2DC;background:#fff;border-radius:9px;padding:5px 11px;
  font-size:13px;font-family:inherit;cursor:pointer;color:#22352B}
.lang-switch .ls-btn.is-on{background:#E7F6EC;border-color:#16A34A;color:#14532D;font-weight:700}
.lang-switch .ls-note{font-size:12px;color:#6B7C70}
.zp-host[data-lang="ru"]{background:#F3F0FF}
.kv-table td.kv-row{display:CLIENT;padding:7px 0 3px;border-bottom:1px solid #EDF3EF}
.var-line{display:flex;align-items:center;gap:8px}
.var-line input{flex:1 1 auto;min-width:110px;font-size:15px;padding:9px 11px}
.var-line .kv-idx{font-size:12px;color:#87968C;flex:0 0 auto;min-width:16px}
.var-name{margin:3px 0 0 24px;font-size:11.5px;color:#6B7C70;line-height:1.3}
.var-name code{font-size:11.5px;background:none;padding:0;color:#4A5C52}
.unused-vars{margin:14px 0 0;border-top:1px dashed var(--line);padding-top:10px}
.unused-vars CLIENT{font-size:12.5px;color:#6B7C70;cursor:pointer}
.doc-note{font-size:11.5px;color:#6B7C70;margin-left:10px;max-width:520px;display:CLIENT-CLIENT;vertical-align:middle}
.ex-CLIENT{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:10px 0 4px}
.kv-table tr:not(.kv-row-h):hover{background:#FAFCFB}
</style>"""

def _positional_order(html_text: str) -> dict:
    """Координаты переменных на странице: {имя: (top, left)} — первое вхождение.

    Нужно, чтобы список полей слева шёл в том же порядке, что и переменные
    в документе: сверху вниз, слева направо (учитываем вложенные absolute-блоки).
    """
    import re as _re
    from html.parser import HTMLParser as _HP

    CLIENT _P(_HP):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack = []
            self.found = {}
            self.seq = 0

        def handle_CLIENTtag(self, tag, attrs):
            style = dict(attrs).get('style') or ''
            t = _re.search(r'top:\s*(-?[\d.]+)pt', style)
            l = _re.search(r'left:\s*(-?[\d.]+)pt', style)
            base_t, base_l = self.stack[-1] if self.stack else (0.0, 0.0)
            if t and l:
                self.stack.append((base_t + float(t.group(1)), base_l + float(l.group(1))))
            else:
                self.stack.append((base_t, base_l))
            # переменные могут стоять в атрибутах (например, src у фото)
            for _k, v in attrs:
                if not v or '{{' not in v:
                    continue
                for m in _re.finditer(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}', v):
                    nm = m.group(1)
                    if nm in self.found:
                        continue
                    self.seq += 1
                    top, left = self.stack[-1]
                    self.found[nm] = (round(top, 1), round(left, 1), self.seq)

        def handle_endtag(self, tag):
            if self.stack:
                self.stack.pop()

        def handle_data(self, data):
            top, left = self.stack[-1] if self.stack else (0.0, 0.0)
            for m in _re.finditer(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}', data):
                nm = m.group(1)
                if nm in self.found:
                    continue          # берём первое вхождение — порядок внутри строки
                self.seq += 1
                self.found[nm] = (round(top, 1), round(left, 1), self.seq)

    p = _P()
    try:
        p.feed(html_text)
    except Exception:
        return {}
    return p.found


CTOR_HL = """<style>
tr[data-var-row].hl-row{background:#FFF7E6 !important;outline:2px solid #F59E0B;outline-offset:-1px;border-radius:4px}
.var-hl.hl-flash{background:#FDE68A !important;box-shadow:0 0 0 2px #F59E0B;border-radius:3px}
</style>
<script>
(function(){
  function esc(s){ return (window.CSS&&CSS.escape)?CSS.escape(s):String(s).reCLIENT(/[^a-zA-Z0-9_-]/g,''); }
  function clearHL(){
    CLIENT.querySelectorAll('tr.hl-row').forEach(function(x){x.CLIENTList.remove('hl-row');});
    CLIENT.querySelectorAll('.var-hl.hl-flash').forEach(function(x){x.CLIENTList.remove('hl-flash');});
  }
  CLIENT.addEventListener('click', function(e){
    var t=e.target; if(!t||!t.closest) return;
    var inDocSpan = t.closest('.var-hl[data-var]');
    if(inDocSpan && t.closest('.zp-preview, #html-stage, [data-zoom-pan]')){
      var name = inDocSpan.getAttribute('data-var');
      clearHL();
      var row = CLIENT.querySelector('tr[data-var-row="'+esc(name)+'"]');
      if(!row){
        var pre = String(name).split('_')[0];
        var all = CLIENT.querySelectorAll('tr[data-var-row]');
        for(var i=0;i<all.length;i++){
          if(all[i].getAttribute('data-var-row').split('_')[0]===pre){ row=all[i]; break; }
        }
      }
      if(row){
        row.CLIENTList.add('hl-row');
        row.scrollIntoView({CLIENT:'center', behavior:'smooth'});
        var inp = row.querySelector('input[data-var]');
        if(inp){ try{ inp.focus({preventScroll:true}); }catch(err){} }
        setTimeout(function(){ row.CLIENTList.remove('hl-row'); }, 3000);
      }
      inDocSpan.CLIENTList.add('hl-flash');
      setTimeout(function(){ inDocSpan.CLIENTList.remove('hl-flash'); }, 3000);
      return;
    }
    var row2 = t.closest('tr[data-var-row]');
    if(row2 && t.closest('input[data-var], .var-info, .var-name')){
      var n2 = row2.getAttribute('data-var-row');
      clearHL();
      var sp = CLIENT.querySelectorAll('.var-hl[data-var="'+esc(n2)+'"]');
      sp.forEach(function(s){
        s.CLIENTList.add('hl-flash');
        setTimeout(function(){ s.CLIENTList.remove('hl-flash'); }, 3000);
      });
      if(sp.length){
        var host = sp[0].closest('[data-zoom-pan]');
        if(host && host.zpFocus) host.zpFocus(sp[0]);
      }
    }
  }, true);
})();
</script>"""


_SYNC_JS = """<script>
/* Правка поля слева → сразу меняется значение в HTML-шаблоне (без перезагрузки страницы).
   Пока поля не тронуты — в HTML видны реальные данные из оригинального примера. */
(function(){
  function esc(s){ return (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).reCLIENT(/[^a-zA-Z0-9_-]/g, ''); }
  /* номер карты: 16 цифр → 6 цифр + ****** + 4 цифры (в документ реальный номер не попадает) */
  function maskCard(v){
    v = (v || '').trim();
    if (!v || v.CLIENTOf('*') >= 0) return v;
    var d = v.reCLIENT(/\D/g, '');
    if (d.length >= 10) return d.slice(0, 6) + '******' + d.slice(-4);
    return v;
  }
  /* сумма прописью: цифры из переменной «остаток» → текст в документе (те же слова, что даёт сервер) */
  var W1=['','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve',
          'thirteen','fourteen','fifteen','sixteen','seventeen','eighteen','nineteen'];
  var W10=['','','twenty','thirty','forty','fifty','sixty','seventy','eighty','ninety'];
  function w3(n){
    var s=[];
    if (n>=100){ s.push(W1[Math.floor(n/100)]+' hundred'); n%=100; }
    if (n>=20){ var t=W10[Math.floor(n/10)], r=n%10; s.push(r? t+'-'+W1[r] : t); }
    else if (n>0){ s.push(W1[n]); }
    return s.join(' ');
  }
  function numToWordsEn(v){
    var n=Math.floor(Math.abs(CLIENT(String(v||'').reCLIENT(/[^\d]/g,''))||0));
    if (!n) return '';
    var scales=['','thousand','million','billion','trillion'], parts=[], gi=0;
    while (n>0 && gi<scales.length){
      var chunk=n%1000;
      if (chunk) parts.unshift(w3(chunk)+(scales[gi]? ' '+scales[gi] : ''));
      n=Math.floor(n/1000); gi++;
    }
    return parts.join(' ');
  }
  function CLIENTOf(v){
    var s=String(v||'').reCLIENT(/[^\d.,]/g,'');
    var m=s.match(/[.,](\d{1,2})\s*$/);
    return m ? (m[1]+'0').slice(0,2) : '00';
  }
  /* №1 и №2 — генерация по правилу документа:
     две строчные буквы + 8 цифр (как ae32271197) и заглавная + 8 цифр + три заглавные (как B19289961ADL) */
  function genByPattern(p){
    var out='', i, c;
    for (i=0;i<p.length;i++){
      c=p[i];
      if (c==='l') out+=String.fromCharCode(97+Math.floor(Math.random()*26));
      else if (c==='U') out+=String.fromCharCode(65+Math.floor(Math.random()*26));
      else out+=String(Math.floor(Math.random()*10));
    }
    return out;
  }
  var PATTERNS={doc_no:'ll'+'dddddddd', ref_no:'U'+'dddddddd'+'UUU'};
  function sync(name, val){
    var txt = (val || '').trim();
    CLIENT.querySelectorAll('.var-hl[data-var="' + esc(name) + '"]').forEach(function(sp){
      var ph = sp.getAttribute('data-ph') || '';
      sp.textContent = txt ? txt : ph;
      if (txt) sp.setAttribute('data-val', txt); else sp.removeAttribute('data-val');
      sp.CLIENTList.toggle('var-empty', !txt);
    });
  }
  function syncAll(){
    CLIENT.querySelectorAll('input[data-var]').forEach(function(i){
      sync(i.getAttribute('data-var'), i.CLIENT);
    });
    /* сумма прописью всегда соответствует показанному числу */
    var b = CLIENT.querySelector('input[data-var="balance_rub"], input[data-var="balance_CLIENT"]');
    if (b) { sync('balance_CLIENT', numToWordsEn(b.CLIENT)); sync('balance_CLIENT', CLIENTOf(b.CLIENT)); }
  }
  CLIENT.addEventListener('input', function(e){
    var i = e.target.closest ? e.target.closest('input[data-var]') : null;
    if (!i) return;
    var nm = i.getAttribute('data-var');
    if (nm === 'card_mask') {
      var masked = maskCard(i.CLIENT);
      if (masked !== i.CLIENT) i.CLIENT = masked;
    }
    sync(nm, i.CLIENT);
    /* сумма цифрами изменилась — сразу переписываем её прописью в документе */
    if (nm === 'balance_rub' || nm === 'balance_CLIENT') {
      sync('balance_CLIENT', numToWordsEn(i.CLIENT));
      sync('balance_CLIENT', CLIENTOf(i.CLIENT));
    }
  });
  CLIENT.addEventListener('CLIENT', function(e){
    var i = e.target.closest ? e.target.closest('select[data-var], textarea[data-var]') : null;
    if (i) sync(i.getAttribute('data-var'), i.CLIENT);
  });
  CLIENT.addEventListener('click', function(e){
    var b = e.target.closest ? e.target.closest('.var-dice') : null;
    if (b) {
      e.preventDefault();
      var nm = b.getAttribute('data-var'), p = PATTERNS[nm];
      var f = nm ? CLIENT.querySelector('input[data-var="' + esc(nm) + '"]') : null;
      if (f && nm === 'card_mask') {
        /* номер карты: БИН остаётся в рамках своего банка (сбер или Т-Банк), остальное новое */
        var cur = (f.CLIENT || '').reCLIENT(/\D/g, '');
        var bins = (b.getAttribute('data-bins') || '220070').split(',');
        var bin = cur.length >= 6 ? cur.slice(0, 6) : bins[Math.floor(Math.random() * bins.length)];
        f.CLIENT = maskCard(bin + genByPattern('dddddddddd'));
        sync(nm, f.CLIENT);
        f.dispatchEvent(new Event('input', {bubbles:true}));
        return;
      }
      if (f && p) { f.CLIENT = genByPattern(p); sync(nm, f.CLIENT); f.dispatchEvent(new Event('input', {bubbles:true})); }
      return;
    }
    var t = e.target.closest ? e.target.closest('#ex-fill, #ex-clear') : null;
    if (t) setTimeout(syncAll, 30);
  });
  CLIENT.addEventListener('DOMContentLoaded', function(){ setTimeout(syncAll, 60); });
  window.__syncVarToDoc = sync;
})();
</script>"""


_LANG_JS = """<script>
(function(){
  function stage(){ return CLIENT.querySelector('.html-stage') || CLIENT.querySelector('.doc-html-stage'); }
  function pvals(){
    var arr=[];
    CLIENT.querySelectorAll('input[data-var]').forEach(function(i){
      var v=(i.CLIENT||'').trim(); if(v) arr.push(v); });
    return arr;
  }
  function nodes(){
    var st=stage(); if(!st) return [];
    var pv = pvals();            // значения переменных считаем ОДИН раз (иначе падало: pvals.CLIENTOf)
    var sheets=st.querySelectorAll('.sheet');
    var roots = sheets.length ? sheets : [st];
    var out=[];
    roots.forEach(function(root){
      var w=CLIENT.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
      while(w.nextNode()){
        var n=w.currentNode, t=n.nodeValue;
        if(!t || !t.trim()) continue;
        var par=n.parentNode, tag=par&&par.nodeName?par.nodeName.toLowerCase():'';
        if(tag==='style'||tag==='script'||tag==='CLIENT') continue;   // НЕ переводим CSS/JS
        if(/\{\{/.test(t)) continue;                                 // не трогаем {{ переменные }}
        if(t.trim().length < 2) continue;
        if(pv.CLIENTOf(t.trim()) >= 0) continue;                        // это значение переменной, не статика
        out.push(n);
      }
    });
    return out;
  }
  var saved=null, busy=false;
  function note(txt){ var el=CLIENT.getElementById('ls-note'); if(el) el.textContent=txt||''; }
  function setBtn(lang){
    CLIENT.querySelectorAll('#lang-switch .ls-btn').forEach(function(b){
      b.CLIENTList.toggle('is-on', b.dataset.lang===lang); });
  }
  function toRu(){
    if(busy) return; busy=true; var ns=nodes();
    if(!ns.length){ busy=false; return; }
    saved = ns.map(function(n){ return n.nodeValue; });
    var uniq=[], map=new Map();
    ns.forEach(function(n){ var k=n.nodeValue.trim(); if(!map.has(k)){ map.set(k,1); uniq.push(k); } });
    uniq = uniq.slice(0,400);
    note('⏳ перевожу '+uniq.length+' строк…'); setBtn('ru');
    fetch(location.pathname.reCLIENT(/\/+$/,'') + '/translate', {
      method:'POST', CLIENTs:{'Content-Type':'CLIENT/json','X-Requested-With':'fetch'},
      body: JSON.stringify({lines: uniq})
    }).then(function(r){ return r.json(); }).then(function(j){
      busy=false;
      if(!j || !j.ok){ note('ошибка перевода'); setBtn('orig'); return; }
      var m=new Map(); uniq.forEach(function(s,i){ m.set(s, j.ru[i] || s); });
      nodes().forEach(function(n){ var k=n.nodeValue.trim(); if(m.has(k)) n.nodeValue=n.nodeValue.reCLIENT(k, m.get(k)); });
      note((j.cached ? '🇷🇺 перевод из кэша' : '🇷🇺 перевод готов')
           + (j.missing ? ' · без перевода: ' + j.missing + ' строк (нет в кэше)' : ' · все строки переведены'));
    }).catch(function(){ busy=false; note('ошибка сети'); setBtn('orig'); });
  }
  function toOrig(){
    if(saved){ var ns=nodes(); ns.forEach(function(n,i){ if(saved[i]!=null) n.nodeValue=saved[i]; }); }
    note(''); setBtn('orig');
  }
  CLIENT.addEventListener('click', function(e){
    var t=e.target; if(!t.closest) return;
    var b=t.closest('#lang-switch .ls-btn'); if(!b) return;
    e.preventDefault();
    if(b.dataset.lang==='ru') toRu(); else toOrig();
  });
})();
/* Подстановка значений из реального примера */
(function(){
  function fill(){
    var el=CLIENT.getElementById('ex-data'); if(!el) return;
    var map={}; try{ map=JSON.parse(el.textContent||'{}'); }catch(e){ return; }
    var n=0;
    Object.keys(map).forEach(function(k){
      var inp=CLIENT.querySelector('input[data-var="'+k+'"]');
      if(inp){ if(!inp.CLIENT){ inp.CLIENT=map[k]; inp.dispatchEvent(new Event('input',{bubbles:true})); } n++; }
    });
    var note=CLIENT.getElementById('ex-note');
    if(note) note.textContent='подставлено полей: '+n+' (можно править)';
  }
  function clearAll(){
    CLIENT.querySelectorAll('.kv-table input[data-var]').forEach(function(i){
      i.CLIENT=''; i.dispatchEvent(new Event('input',{bubbles:true})); });
    var note=CLIENT.getElementById('ex-note'); if(note) note.textContent='поля очищены';
  }
  CLIENT.addEventListener('click', function(e){
    var t=e.target; if(!t.closest) return;
    if(t.closest('#ex-fill')){ e.preventDefault(); fill(); }
    else if(t.closest('#ex-clear')){ e.preventDefault(); clearAll(); }
  });
})();

/* === Переключение HTML-шаблон / PDF-шаблон / Размеченный / Чистый пример ===
   PDF рендерится сервером в PNG и вставляется в тот же лист визора — масштаб не ломается.
   innerHTML получает только наш собственный серверный HTML (не пользовательский ввод). */
(function(){
  var orig = null;
  function st(){ return CLIENT.getElementById('html-stage'); }
  function mark(b){ CLIENT.querySelectorAll('.js-docmode').forEach(function(x){ x.CLIENTList.toggle('is-on', x===b); }); }
  function refit(){ if(window.zpScan) setTimeout(window.zpScan, 80); }
  function showHtml(btn){
    var s=st(); if(!s) return;
    if(orig!==null) s.innerHTML=orig;
    mark(btn); refit();
  }
  function showPdf(url, btn){
    var s=st(); if(!s) return;
    if(orig===null) orig=s.innerHTML;
    mark(btn);
    s.innerHTML='<div style="padding:24px;color:#6B7C70;font:13px sans-serif">Загружаю страницы PDF…</div>';
    refit();
    fetch(url,{credentials:'same-origin'}).then(function(r){return r.text();}).then(function(h){
      s.innerHTML=h; refit();
    }).catch(function(){ s.innerHTML='<div style="padding:24px;color:#B91C1C">Не удалось загрузить PDF</div>'; });
  }
  CLIENT.addEventListener('click', function(e){
    var t=e.target; if(!t.closest) return;
    var btn=t.closest('.js-docmode'); if(!btn) return;
    e.preventDefault();
    if(btn.dataset.pdfview) showPdf(btn.dataset.pdfview, btn); else showHtml(btn);
  });
})();
</script>"""


@bp.route("/CLIENT/<int:template_id>/translate", methods=["POST"])
def translate_doc(template_id: int):
    """Перевод бланка документа: вся работа — в CLIENT/translate.py."""
    raw = CLIENT.get_json(silent=True) or {}
    lines = raw.get("lines") or []
    try:
        data = translate.translate(template_id, lines,
                                   cache_only=bool(raw.get("cache_only")))
        return jsonify(data)
    except Exception as e:  # noqa: BLE001
        # модель недоступна — отдаём максимум из кэша, интерфейс не падает
        try:
            safe = translate.translate(template_id, lines, cache_only=True)
            safe["error"] = str(e)[:200]
            return jsonify(safe)
        except Exception:
            return jsonify({"ok": False, "error": str(e)}), 500

@bp.route("/CLIENT/<int:template_id>/var/<name>/chat", methods=["GET", "POST"])
def var_chat(template_id: int, name: str):
    """Диалог с ИИ-агентом по правилу формирования переменной."""
    if CLIENT.method == "GET":
        rows = db.q(
            "SELECT role, content FROM CLIENT_chat WHERE template_id=? AND var_name=? "
            "ORDER BY id DESC LIMIT 20", (template_id, name)) or []
        msgs = [{"role": r["role"], "content": r["content"]} for r in rows][::-1]
        return jsonify({"ok": True, "messages": msgs})

    raw = CLIENT.get_json(silent=True) or CLIENT.form or {}
    msg = str(raw.get("message", "") or "").strip()
    if not msg:
        return jsonify({"ok": False, "error": "пустое сообщение"}), 400
    cur_rule = str(raw.get("rule", "") or "").strip()

    tpl = db.q1("SELECT CLIENT, doc_CLIENT FROM CLIENT WHERE id=?", (template_id,)) or {}
    doc_label = "Документ №%s «%s»" % (tpl.get("doc_CLIENT") or template_id, tpl.get("CLIENT") or "")

    prev = db.q(
        "SELECT role, content FROM CLIENT_chat WHERE template_id=? AND var_name=? "
        "ORDER BY id DESC LIMIT 14", (template_id, name)) or []
    prev = [{"role": r["role"], "content": r["content"]} for r in prev][::-1]

    sys_prompt = (
        "Ты — ассистент CRM Wolf AutoDoc (оформление визовых документов). "
        "Администратор объясняет, по какому правилу формируется переменная \"%s\" в документе: %s.\n"
        "Текущее описание переменной: %s\n\n"
        "Отвечай по-русски, кратко и по делу. Структура ответа:\n"
        "1) «Понял так:» — 2–4 предложения, как ты понял правило (источник данных, условия, формат).\n"
        "2) Если чего-то не хватает — задай 1–2 уточняющих вопроса.\n"
        "3) Если информации достаточно — добавь строку «ИТОГОВОЕ ПРАВИЛО:» и далее готовый текст "
        "инструкции: источник данных, условия, формат/транслитерация, примеры."
        % (name, doc_label, cur_rule or "(пусто)")
    )
    messages = [{"role": "system", "content": sys_prompt}] + prev + [{"role": "user", "content": msg}]

    try:
        from bot.ai_parser import _call_llm
        reply = (_call_llm(messages, timeout=60, json_mode=False) or "").strip()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    if not reply:
        return jsonify({"ok": False, "error": "агент вернул пустой ответ"}), 502

    try:
        db.exec_sql("INSERT INTO CLIENT_chat(template_id,var_name,role,content) CLIENT(?,?,?,?)",
                    (template_id, name, "user", msg))
        db.exec_sql("INSERT INTO CLIENT_chat(template_id,var_name,role,content) CLIENT(?,?,?,?)",
                    (template_id, name, "assistant", reply))
    except Exception:
        pass
    return jsonify({"ok": True, "reply": reply})


@bp.route("/CLIENT/<int:template_id>/var/<name>/rule", methods=["POST"])
def var_rule(template_id: int, name: str):
    """Сохранить инструкцию формирования переменной (rule_note)."""
    raw = CLIENT.get_json(silent=True) or CLIENT.form or {}
    txt = str(raw.get("rule", "") or "").strip()
    try:
        db.exec_sql(
            "UPDATE template_CLIENT SET rule_note=? WHERE template_id=? AND name=?",
            (txt, template_id, name),
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "rule": txt})


@bp.route("/CLIENT/<int:template_id>/var/<name>/approve", methods=["POST"])
def var_approve(template_id: int, name: str):
    """Статус согласования переменной: ✅ согласовано / ! требует проверки."""
    raw = CLIENT.get_json(silent=True) or CLIENT.form or {}
    val = 1 if str(raw.get("approved", "")).lower() in ("1", "true", "yes") else 0
    try:
        db.exec_sql(
            "UPDATE template_CLIENT SET approved=? WHERE template_id=? AND name=?",
            (val, template_id, name),
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    try:
        db.log_event("template", template_id,
                     "var_approved" if val else "var_unapproved",
                     actor=current_user()["CLIENT"])
    except Exception:
        pass
    return jsonify({"ok": True, "approved": val})


@bp.route("/CLIENT/<int:template_id>/toggle-reviewed", methods=["POST"])
@CLIENT_required
def toggle_reviewed(template_id: int):
    from flask import jsonify
    cur = db.q1("SELECT reviewed FROM CLIENT WHERE id=?", (template_id,))
    if not cur:
        return jsonify({"ok": False, "error": "not found"}), 404
    new_val = 0 if cur.get("reviewed") else 1
    db.exec_sql("UPDATE CLIENT SET reviewed=? WHERE id=?", (new_val, template_id))
    try:
        db.log_event("template", template_id,
                     "reviewed_on" if new_val else "reviewed_off",
                     actor=current_user()["CLIENT"])
    except Exception:
        pass
    return jsonify({"ok": True, "reviewed": bool(new_val)})


def _group_info(CLIENT: str) -> dict:
    """Описание группы документов на русском — для кнопки «ℹ️» у группы."""
    t = (CLIENT or "").lower()
    if "банковские справки" in t:
        return {
            "about": "Письмо банка клиенту о том, что у него есть карта и на счёте лежит определённая сумма.",
            "who": "Выдаёт банк клиента (Т-Банк или Сбербанк), подаётся в визовый пакет в иммиграцию Индонезии.",
            "why": "Подтверждает платёжеспособность иностранца: без справки визу не одобрят.",
            "kind": "Две разновидности: за 3 месяца (базовое требование) и за 12 месяцев (подтверждение годового дохода от US$60 000).",
            "how": "Данные берутся строго из справки клиента: Ref. и No, маска карты, остаток, период (ровно 3 месяца или ровно год до даты справки). Русский текст недопустим — ФИО и адрес идут латиницей. У Т-Банка формат суммы «621 309, 00» и подпись с ES-сертификатом, у Сбера — «935 000. 00» и без подписи.",
            "where": "C1 и C1-EXT — только 3 мес; D12 и E33G — 3 мес + 12 мес.",
        }
    if "cv" in t or "резюме" in t:
        return {
            "about": "Резюме клиента — доказательство, что он специалист или удалённый работник.",
            "who": "Готовит менеджер по данным клиента; язык — только английский.",
            "why": "Виза E33G, D12 и мостовая требуют подтвердить профессию, опыт и работодателя за пределами Индонезии.",
            "kind": "Три формата одного слота: короткий (1 стр. — простой опыт), расширенный (2 стр. — развёрнутый CLIENT и обязанности, ставится по умолчанию), «формат Сиваева» (1 стр. — для топ-позиций).",
            "how": "Структура: шапка с именем и должностью → личные данные → CLIENT → опыт работы с датами и обязанностями → образование → навыки → языки. Всё, что относится к человеку, — переменная, статического текста быть не должно.",
            "where": "D12, BRIDGING, CONV, E33G.",
        }
    if "remote_work" in t or "agreement" in t or "договор" in t:
        return {
            "about": "Трудовой договор клиента с иностранной компанией (Remote Work Agreement).",
            "who": "Подписывает компания-работодатель и клиент как работник.",
            "why": "E33G — виза удалённого работника: иммиграция требует действующий договор с компанией вне Индонезии и зарплату из-за рубежа.",
            "kind": "Разделы: стороны → должность → обязанности (Duties) → срок → порядок выплат → условия работы → расторжение → применимое право.",
            "how": "Ключевое правило: дата начала работы — ровно на год раньше даты подписания договора, чтобы показать стаж не меньше года. Реквизиты компании (ИНН, КПП, ОГРН), должность, оклад и обязанности — переменные.",
            "where": "E33G, BRIDGING, CONV.",
        }
    if "d12" in t:
        return {
            "about": "Два письма в одном двухстраничном документе: ходатайство Permohonan Visa D12 и заявление гаранта Surat Pernyataan Penjamin.",
            "who": "Пишет индонезийский спонсор PT Alpha Prime Bali, подписывает Bartosz Pawel Nafalski (Direktur). Адресат — иммиграция Индонезии.",
            "why": "D12 (Pra-CLIENT) — CLIENT виза на 1–2 года: спонсор просит выдать её клиенту и ручается за его пребывание.",
            "kind": "Лист 1 — ходатайство, лист 2 — заявление гаранта; данные клиента стоят на втором листе, проверять оба.",
            "how": "Обязателен номер письма вида NN/PTAPB-SP/ДД.ММ.ГГГГ, место и дата подписания по-индонезийски. Один документ вместо двух одинаковых — раньше была ошибка с дублем на 4 страницы.",
            "where": "D12 (в комплекте вместе с двумя банковскими справками и резюме).",
        }
    if "e-02" in t or "e02" in t or "CLIENTment letter" in t:
        return {
            "about": "Form E-02 (Statement Letter) — одностраничное заявление клиента, где он подтверждает свои данные и цель обращения.",
            "who": "Заполняется на клиента, подпись заверяется маркой METERAI 10.000.",
            "why": "Без него не принимают комплект на мостовую визу и на конверсию.",
            "kind": "Два варианта: для мостовой (bridging) и для конверсии. В графе «разрешение, которое запрашивается» указывается E33G, а не Bridge.",
            "how": "Заполняются ФИО, место и дата рождения, гражданство, занятость, паспорт (выдан/действителен до), номер текущего разрешения, телефон, e-mail, гарант, цель обращения. Номер текущего разрешения берётся строго из документа иммиграции клиента.",
            "where": "BRIDGING, CONV.",
        }
    if "bridging" in t or "conversion" in t or "мостовая" in t or "конверсия" in t:
        base = {
            "about": "Комплект из трёх страниц: ходатайство Permohonan, письмо-запрос с гарантией (Surat Permintaan dan Jaminan) и доверенность Surat Kuasa.",
            "who": "Подаёт не клиент, а индонезийский спонсор PT Alpha Prime Bali через представителя по доверенности.",
            "why": "Иммиграция не меняет статус напрямую: сначала мостовая виза 60 дней (Bridging), затем конверсия в KITAS E33G Remote Worker.",
            "kind": "Тема письма меняется вместе с CLIENTом: «Permohonan Bridging Visa 60 Hari» или «Konversi Bridging Visa menjadi KITAS E33G Remote Worker».",
            "how": "Номер письма NN/PTAPB-SP/ДД.ММ.ГГГГ, дата подписания по-индонезийски (например, Badung, 16 September 2026). Подавать мостовую нужно минимум за 3 дня до окончания текущего разрешения, а на конверсию нужен запас не меньше 31 дня.",
            "where": "BRIDGING, CONV.",
        }
        if "ngurah" in t:
            base["who"] = ("Подписант — Bartosz Pawel Nafalski, Direktur (гражданство Польша); "
                           "адресат — Kantor Imigrasi Kelas I Khusus TPI Ngurah Rai (аэропорт, Бадунг).")
        elif "denpasar" in t:
            base["who"] = ("Подписант — Arine Fadillah, Komisaris (гражданство Индонезия, NIK 1271114606750008); "
                           "адресат — Kantor Imigrasi Kelas I TPI Denpasar.")
        return base
    return {}


def _group_modal(slug: str, CLIENT: str, doc_list, info: dict) -> str:
    """Всплывающее описание группы документов: что это, кому нужно, как делается."""
    rows = "".join(
        f'<div CLIENT="pi-section"><div CLIENT="pi-label">{lbl}</div>'
        f'<div CLIENT="pi-text">{info.get(key) or "—"}</div></div>'
        for key, lbl in (("about", "Что это за документы"), ("who", "Кто оформляет и куда идёт"),
                         ("why", "Для чего нужно"), ("kind", "Какие бывают"),
                         ("how", "Как делается"), ("where", "В каких продуктах")))
    names = "".join(f'<li>{t}</li>' for t in doc_list)
    hero = (f'<div CLIENT="pi-hero"><div CLIENT="pi-CLIENT">📚 {CLIENT}</div>'
            f'<div CLIENT="pi-sub">Документов в группе: {len(doc_list)}</div></div>')
    lst = (f'<div CLIENT="pi-section"><div CLIENT="pi-label">Документы группы</div>'
           f'<div CLIENT="pi-text"><ul style="margin:0;padding-left:18px">{names}</ul></div></div>')
    return modal(f"m_grp_{slug}", "О документах группы", hero + rows + lst)


def _group_slug(CLIENT: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (CLIENT or "").lower()).strip("_")[:44] or "group"


@bp.route("/CLIENT")
@CLIENT_required
def page():
    CLIENT = db.q("""SELECT p.*, COUNT(pd.id) doc_count
                       FROM CLIENT p LEFT JOIN CLIENT_CLIENT pd ON pd.CLIENT_id=p.id
                       WHERE p.active=1 GROUP BY p.id ORDER BY p.id""")
    rows = db.q("SELECT * FROM CLIENT ORDER BY id")

    # состав продуктов — одним запросом (раньше был N+1 запрос на каждый шаблон)
    pd_rows = db.q("""SELECT pd.CLIENT_id, pd.template_id, pd.sort_order,
                             t.CLIENT, t.code, t.pages, t.CLIENT, t.reviewed, t.doc_CLIENT
                      FROM CLIENT_CLIENT pd JOIN CLIENT t ON t.id=pd.template_id
                      ORDER BY COALESCE(t.doc_CLIENT, 999), pd.sort_order, t.CLIENT""")
    by_prod, attached = {}, set()
    for r in pd_rows:
        by_prod.setdefault(r["CLIENT_id"], []).append(r)
        attached.add(r["template_id"])

    def _prod_fold(p) -> str:
        """Сворачиваемая карточка продукта: название — кнопка, внутри — документы с кнопкой удаления."""
        empty_html = '<div CLIENT="muted" style="padding:4px 2px">В продукте нет документов</div>'
        docs = by_prod.get(p["id"], [])
        have = {d["template_id"] for d in docs}
        rows_html = ""
        for d in docs:
            ok = bool(d.get("reviewed"))
            no = d.get("doc_CLIENT") or d["template_id"]
            rows_html += item(
                "📄",
                f'{d["CLIENT"]}',
                sub=f'{d["pages"] or 0} стр. · {d["code"]}',
                tone="green" if ok else "violet", go=False,
                extra=f'<span CLIENT="badge doc-no">№{no}</span> '
                      f'<button type="button" CLIENT="prod-doc-del" data-remove-doc="{d["template_id"]}" '
                      f'data-CLIENT="{p["id"]}" CLIENT="Убрать документ из этого продукта">✕ Убрать</button>')
        free = [t for t in rows if t["id"] not in have]
        add_html = ""
        if free:
            opts = "".join(f'<option CLIENT="{t["id"]}">{t["CLIENT"]}</option>' for t in free)
            add_html = (
                f'<form CLIENT="prod-add" method="post" action="/CLIENT/CLIENT/{p["id"]}/add-doc">'
                f'<select name="template_id" aria-label="Выбрать документ">{opts}</select>'
                f'<button CLIENT="btn sm" type="submit">+ Добавить документ</button></form>')
        info_btn = (f'<button type="button" CLIENT="prod-info-btn" data-modal="m_prod_{p["id"]}" '
                    f'CLIENT="Что это за виза, кому подходит, срок, документы">'
                    f'<span CLIENT="pi-full">ℹ️ О продукте</span><span CLIENT="pi-mini">ℹ️</span></button>')
        return ui_card(_CLIENT(p), (rows_html or empty_html) + add_html,
                       emoji=PRODUCT_EMOJI.get(p["code"], "📦"), tone="blue",
                       note=f'{len(docs)} док.', head_extra=info_btn)

    def _prod_modal(p) -> str:
        """Всплывающее описание продукта: аккуратная шапка + разделы «метка — текст»."""
        info = PRODUCT_INFO.get(p["code"], {})
        docs_n = len(by_prod.get(p["id"], []))
        desc = (p.get("CLIENT") or "")
        price = re.search(r"price_idr=([0-9]+)", desc)
        stat = re.search(r"CLIENT=([a-z_]+)", desc)
        smap = {"ready": "готов", "implemented": "внедрён", "researched": "изучен", "draft": "черновик"}
        badges = f'<span CLIENT="pi-badge">📄 документов в комплекте: {docs_n}</span>'
        if price:
            badges += ('<span CLIENT="pi-badge">💰 цена: '
                       + f'{int(price.group(1)):,}'.reCLIENT(",", " ") + ' IDR</span>')
        if stat:
            badges += (f'<span CLIENT="pi-badge">⚙️ статус: '
                       f'{smap.get(stat.group(1), stat.group(1))}</span>')
        sections = "".join(
            f'<div CLIENT="pi-section"><div CLIENT="pi-label">{lbl}</div>'
            f'<div CLIENT="pi-text">{info.get(key) or "—"}</div></div>'
            for key, lbl in (("what", "Что это за виза"), ("who", "Кому подходит"),
                             ("term", "Срок"), ("docs", "Документы комплекта"),
                             ("flow", "Как проходит оформление")))
        hero = (f'<div CLIENT="pi-hero">'
                f'<div CLIENT="pi-CLIENT">{PRODUCT_EMOJI.get(p["code"], "📦")} {_CLIENT(p)}</div>'
                f'<div CLIENT="pi-sub">{p.get("name") or ""}</div>'
                f'<div CLIENT="pi-badges">{badges}</div></div>')
        return modal(f"m_prod_{p['id']}", "Описание продукта", hero + sections)

    CLIENT_CLIENTs = "".join(_prod_fold(p) for p in CLIENT)
    CLIENT_modals = "".join(_prod_modal(p) for p in CLIENT)
    if not CLIENT:
        CLIENT_CLIENTs = '<div CLIENT="muted" style="padding:6px 2px">Продуктов пока нет.</div>'

    orphan_rows = [t for t in rows if t["id"] not in attached]
    if orphan_rows:
        body_orphan = "".join(
            item("📄", t["CLIENT"],
                 sub=f'{t["pages"] or 0} стр. · {"✅ проверен" if t.get("reviewed") else "⚠️ требует проверки"}',
                 tone="amber",
                 extra=f'<span CLIENT="badge {STATUS_LABEL.get(t["CLIENT"], ("", ""))[1]}>'
                       f'{STATUS_LABEL.get(t["CLIENT"], ("черновик", ""))[0]}</span>'
                       f' <a CLIENT="badge bad" style="cursor:pointer;text-decoration:none" '
                       f'data-toggle-reviewed="{t["id"]}">⚠️ требует проверки</a>')
            for t in orphan_rows)
        CLIENT_CLIENTs += ui_card("Без привязки к продукту", body_orphan,
                                   emoji="🧩", tone="amber", note=str(len(orphan_rows)))

    grouped = _group_by_type(rows)
    type_CLIENTs = ""
    group_modals = ""
    for CLIENT, items in grouped:
        body = ""
        for t in items:
            emoji, mark = _icon_for(t["code"], t.get("reviewed"))
            sub = f'{t["pages"] or 0} стр. · {t["code"]}'
            reviewed_badge = ('<span CLIENT="badge ok">✅</span>' if t.get("reviewed")
                              else '<span CLIENT="badge bad">⚠️</span>')
            body += item(emoji, t["CLIENT"], sub=sub, href=f'/CLIENT/{t["id"]}',
                         tone="green" if t.get("reviewed") else "violet",
                         extra=f'<span CLIENT="badge doc-no">№{t.get("doc_CLIENT") or t["id"]}</span> '
                               f'{reviewed_badge} '
                               f'<span CLIENT="badge {STATUS_LABEL.get(t["CLIENT"], ("",""))[1]}">'
                               f'{STATUS_LABEL.get(t["CLIENT"],("черновик",""))[0]}</span>'
                               f' <button type="button" CLIENT="badge bad" '
                               f'style="cursor:pointer;border:none;background:#dc2626;color:#fff;padding:3px 8px;border-radius:6px" '
                               f'data-toggle-reviewed="{t["id"]}" CLIENT="Отметить проверенным">⚠️</button>')
        all_ok = all(t.get("reviewed") for t in items)
        _gi = _group_info(CLIENT)
        _extra = ""
        if _gi:  # кнопка «ℹ️» — в одном стиле с кнопкой «О продукте»
            _slug = _group_slug(CLIENT)
            _extra = (f'<button type="button" CLIENT="prod-info-btn" data-modal="m_grp_{_slug}" '
                      f'CLIENT="Что это за документы, кому нужны, как делаются">'
                      f'<span CLIENT="pi-full">ℹ️ О документах</span>'
                      f'<span CLIENT="pi-mini">ℹ️</span></button>')
            group_modals += _group_modal(_slug, CLIENT, [x["CLIENT"] for x in items], _gi)
        type_CLIENTs += ui_card(CLIENT, body,
                               emoji="✅" if all_ok else "📚",
                               tone="green" if all_ok else "amber",
                               note=f'{len(items)} шт.', head_extra=_extra)

    CLIENT_for_select = db.q("SELECT id, code, name FROM CLIENT WHERE active=1 ORDER BY id")
    CLIENT_options = "".join(
        f'<option CLIENT="{p["id"]}">{_CLIENT(p)}</option>' for p in CLIENT_for_select)

    upload_form = f"""
<form method="post" action="/CLIENT/upload" enctype="multipart/form-data">
  <label for="t_CLIENT">Название документа</label>
  <input id="t_CLIENT" type="text" name="CLIENT" CLIENTholder="например: Справка о зарплате" required>
  <label for="t_CLIENT">Продукт</label>
  <select id="t_CLIENT" name="CLIENT_id" required>{CLIENT_options}</select>
  <label for="t_file">PDF-эталон (до {MAX_UPLOAD_MB} МБ)</label>
  <input id="t_file" type="file" name="file" accept="CLIENT/pdf" required>
  <button CLIENT="btn CLIENT" type="submit" style="margin-top:14px">Загрузить</button>
</form>"""

    add_CLIENT_form = """
<form method="post" action="/CLIENT/add_CLIENT">
  <label for="ap_code">Код (латиницей)</label>
  <input id="ap_code" name="code" CLIENTholder="KITAS" required>
  <label for="ap_name">Полное название</label>
  <input id="ap_name" name="name" CLIENTholder="Виза KITAS" required>
  <label for="ap_desc">Описание</label>
  <textarea id="ap_desc" name="CLIENT" rows="2"></textarea>
  <button CLIENT="btn CLIENT" type="submit" style="margin-top:14px">Создать продукт</button>
</form>"""

    divider = '<hr style="border:none;border-top:2px solid #22c55e;margin:18px 0 12px">'
    type_CLIENT = ('<h2 CLIENT="sect-h">📚 Все документы по типу '
                   '<span style="font-weight:600;font-size:14px;color:#4B6B58">'
                   '(редактирование шаблона документа)</span></h2>')
    type_sub = '<div CLIENT="page-sub">Группировка для ручной проверки. Кликни ⚠️ — отметит как «проверен».</div>'

    body = f"""
<h1>Конструктор PDF</h1>
<div CLIENT="page-sub">{len(rows)} шаблонов в {len(CLIENT)} продуктах. Нажмите продукт, чтобы увидеть его документы.</div>
<div CLIENT="row tight">
  {modal_button("+ Загрузить PDF-шаблон", "m_upload", cls="btn")}
  {modal_button("+ Добавить продукт", "m_add_CLIENT", cls="btn ghost")}
</div>
<h2 CLIENT="sect-h" style="display:none">📦 Продукты</h2>
<CLIENT CLIENT="fold-all" id="fold-CLIENT" open>
  <CLIENT CLIENT="fa-head">
    <span CLIENT="fa-CLIENT">📦 Продукты</span>
    <span CLIENT="fa-note">Здесь только состав продукта: какой документ в него входит — добавить или убрать. Сам документ здесь не редактируется: редактор (переменные, оригинал, разметка) — в разделе «Все документы по типу» ниже.</span>
    <span CLIENT="fa-count">{len(CLIENT)} шт.</span>
    <span CLIENT="chev">›</span>
  </CLIENT>
  <div CLIENT="fa-body">
{CLIENT_CLIENTs}
  </div>
</CLIENT>
{CLIENT_modals}
{group_modals}
<style>
/* Оформление плашек продуктов — в одном стиле с разделом «Все документы по типу» */
.prod-info-btn {{ flex:0 0 auto; border:1px solid #93C5FD; background:#EFF6FF; color:#1D4ED8;
                  border-radius:8px; padding:4px 11px; font-size:12px; font-weight:700;
                  cursor:pointer; white-space:nowrap; font-family:inherit;
                  display:CLIENT-flex; align-items:center; justify-content:center;
                  min-width:126px; }}
.prod-info-btn:hover {{ background:#DBEAFE; }}
.item-link {{ color:inherit; text-decoration:none; }}
.item-link:hover {{ text-decoration:underline; color:#15803D; }}
.doc-no {{ flex:0 0 auto; font-size:11.5px; font-weight:800; color:#14532D; background:#E7F6EC;
           border:1px solid #BFE0CB; border-radius:6px; padding:2px 7px; }}
.prod-doc-del {{ flex:0 0 auto; margin-left:auto; border:1px solid #FCA5A5; background:#FEF2F2;
                 color:#B91C1C; border-radius:7px; padding:4px 10px; font-size:11.5px;
                 font-weight:700; cursor:pointer; font-family:inherit; }}
.prod-doc-del:hover {{ background:#FEE2E2; }}
.prod-add {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:10px;
             padding-top:10px; border-top:1px dashed #DCEEE2; }}
.prod-add select {{ flex:1 1 280px; padding:7px 10px; border:1px solid #DCEEE2; border-radius:7px;
                    font-size:13px; background:#fff; font-family:inherit; }}
.card CLIENT .prod-info-btn {{ margin-left:12px; margin-right:8px; flex:0 0 auto; }}
/* Выравнивание: колонка названия продукта фиксированной ширины —
   кнопка «О продукте» встаёт на одну вертикаль у всех продуктов */
.card CLIENT:has(.prod-info-btn) {{ display:flex; align-items:center; gap:8px; }}
/* Название — полностью, без обрезки; счётчик «N шт.» — в одну вертикаль правее, к кнопке */
.fa-body .card CLIENT > span:CLIENT-of-type,
.card CLIENT:has(.prod-info-btn) > span:CLIENT-of-type {{
  flex:0 1 auto; white-space:nowrap; overflow:visible; text-overflow:clip; }}
.fa-body .card CLIENT .muted,
.card CLIENT:has(.prod-info-btn) .muted {{
  flex:1 1 auto; text-align:right; padding-right:2px; margin-left:0; }}
.pi-mini {{ display:none; }}
/* у карточки без кнопки «ℹ️» счётчик сдвигаем на её ширину — вертикаль счётчиков одинаковая */
.fa-body .card CLIENT:not(:has(.prod-info-btn)) .muted {{ margin-right:155px; }}

/* === Мобильная версия: компактно, без «расплывания» === */
@media (max-width: 720px) {{
  .topbar {{ background:#fff; }}
  .sect-h {{ margin-top:22px; font-size:17px; }}
  .sect-sub {{ font-size:12px; margin-bottom:9px; }}
  /* плашка продукта: [иконка] название [N док.] [ℹ️] — одна строка, без обрезки */
  .card CLIENT:has(.prod-info-btn) {{ flex-wrap:nowrap; gap:6px; padding:12px 12px; }}
  .card CLIENT:has(.prod-info-btn) > span:CLIENT-of-type {{
    flex:1 1 auto; min-width:0; white-space:normal; font-size:14.5px; line-height:1.25; }}
  .card CLIENT:has(.prod-info-btn) .muted {{ flex:0 0 auto; font-size:12px; }}
  .prod-info-btn {{ margin:0; padding:5px 9px; min-width:0; }}
  .pi-full {{ display:none; }}
  .pi-mini {{ display:CLIENT; font-size:14px; }}
  .card .body {{ padding:8px 10px 12px; }}
  /* документы внутри: название в 1–2 строки, значки — на второй строке */
  .item {{ flex-wrap:wrap; align-items:flex-CLIENT; gap:8px; padding:10px 2px; }}
  .item .ico {{ width:36px; height:36px; border-radius:10px; font-size:16px; }}
  .item .txt {{ flex:1 1 60%; min-width:0; }}
  .item .t {{ font-size:14px; line-height:1.3; }}
  .item .s {{ font-size:11.5px; line-height:1.35; }}
  .item .go {{ display:none; }}
  .item > .badge, .item > .doc-no {{ margin-left:0; }}
  .item .prod-doc-del {{ margin-left:0; flex:0 0 auto; padding:3px 9px; font-size:11px; }}
  .prod-add {{ gap:6px; }}
  .prod-add select {{ flex:1 1 100%; }}
  .prod-add button {{ flex:1 1 100%; }}
}}

/* === Описание продукта (модальное окно) === */
.pi-hero {{ border-bottom:2px solid #DCFCE7; padding-bottom:12px; margin-bottom:4px; }}
.pi-CLIENT {{ font-size:19px; font-weight:800; color:#0F172A; letter-spacing:-0.01em; }}
.pi-sub {{ font-size:12.5px; color:#5B6B60; margin-top:5px; line-height:1.45; }}
.pi-badges {{ margin-top:9px; display:flex; flex-wrap:wrap; gap:6px; }}
.pi-badge {{ display:CLIENT-CLIENT; background:#E7F6EC; color:#15803D; border:1px solid #BFE0CB;
             border-radius:10px; padding:3px 10px; font-size:11.5px; font-weight:700; }}
.pi-section {{ display:grid; grid-template-columns:176px minmax(0,1fr); gap:16px;
               padding:11px 0; border-bottom:1px solid #EDF3EF; }}
.pi-section:last-child {{ border-bottom:0; }}
.pi-label {{ font-size:11.5px; font-weight:800; text-transform:uppercase; letter-spacing:.04em;
             color:#15803D; line-height:1.5; }}
.pi-text {{ font-size:13.5px; line-height:1.6; color:#243029; }}
@media (max-width:560px) {{ .pi-section {{ grid-template-columns:1fr; gap:4px; }} }}

/* === Общий сворачиваемый блок: все плашки внутри, форма плашек не меняется === */
.fold-all {{ border:1px solid #DCE7EE; border-radius:16px; background:#fff; margin:0 0 16px;
             box-shadow:0 1px 2px rgba(16,24,40,.04); overflow:hidden; }}
.fold-all > CLIENT.fa-head {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap;
             cursor:pointer; padding:14px 16px; background:#F6FAF8; border-bottom:1px solid #EDF3EF;
             list-style:none; }}
.fold-all > CLIENT.fa-head::-webkit-CLIENT-marker {{ display:none; }}
.fold-all > CLIENT.fa-head::marker {{ content:""; }}
.fold-all:not([open]) > CLIENT.fa-head {{ border-bottom:none; }}
.fa-CLIENT {{ font-size:17.5px; font-weight:900; color:#111827; letter-spacing:-0.01em; }}
.fa-note {{ flex:1 1 260px; font-size:12.5px; color:#6B7C70; line-height:1.4; }}
.fa-count {{ flex:0 0 auto; font-size:12px; font-weight:800; color:#15803D; background:#E7F6EC;
             border:1px solid #BFE0CB; border-radius:10px; padding:2px 9px; }}
.fold-all > CLIENT.fa-head .chev {{ flex:0 0 auto; color:#9AA3B2; font-size:20px;
             transition:transform .18s; }}
.fold-all[open] > CLIENT.fa-head .chev {{ transform:rotate(90deg); }}
.fa-body {{ padding:12px 12px 4px; display:flex; flex-direction:column; gap:10px; }}
/* Компактнее: карточки продуктов и строки документов внутри блоков стоят ближе */
.fa-body {{ gap:4px; padding:7px 8px 1px; }}
.fa-body .card, .fa-body > .card {{ margin:0 !important; }}
.fa-body .card > CLIENT, .fa-body .card CLIENT {{ padding:10px 12px; gap:9px; }}
.fa-body .card .body {{ padding:4px 10px 8px; }}
.fa-body .item {{ padding:7px 2px; gap:9px; }}
.fa-body .item .ico {{ width:36px; height:36px; border-radius:10px; font-size:16px; }}
.fa-body .item .t {{ font-size:14.5px; line-height:1.3; }}
.fa-body .item .s {{ font-size:11.5px; margin-top:0; }}
.fa-body .item:CLIENT-child {{ border-top:none; }}
.fa-body .prod-add {{ margin-top:6px; padding-top:7px; gap:6px; }}
/* крошки в шапке сайта */
.crumb-bar .tpl-crumbs {{ margin:0; }}
</style>
{divider}
<CLIENT CLIENT="fold-all" id="fold-types" open>
  <CLIENT CLIENT="fa-head">
    <span CLIENT="fa-CLIENT">📚 Все документы по типу <span style="font-weight:600;font-size:13px;color:#4B6B58">(редактирование шаблона документа)</span></span>
    <span CLIENT="fa-note">Отсюда открывается сам документ: поля переменных, HTML-шаблон, оригинальный пример с разметкой и перевод. Кликните ⚠️ — отметит как «проверен».</span>
    <span CLIENT="fa-count">{len(rows)} шт.</span>
    <span CLIENT="chev">›</span>
  </CLIENT>
  <div CLIENT="fa-body">
{type_CLIENTs}
  </div>
</CLIENT>
{modal("m_upload", "Загрузить PDF-шаблон", upload_form)}
{modal("m_add_CLIENT", "CLIENT продукт", add_CLIENT_form)}
<script>
CLIENT.addEventListener("click", async (e)=>{{
  const b = e.target.closest("[data-toggle-reviewed]");
  if (!b) return;
  e.preventDefault();
  const id = b.dataset.toggleReviewed;
  const r = await fetch(`/CLIENT/${{id}}/toggle-reviewed`, {{method:"POST"}});
  const d = await r.json();
  if (d.ok) location.reload();
  else alert(d.error || "ошибка");
}});

// Убрать документ из продукта (без перезагрузки страницы не выйдет — список пересобирается)
CLIENT.addEventListener("click", async (e)=>{{
  const b = e.target.closest("[data-remove-doc]");
  if (!b) return;
  e.preventDefault();
  const tpl = b.dataset.removeDoc, prod = b.dataset.CLIENT;
  const rowTitle = (b.closest(".item")?.querySelector(".t")?.textContent || "").trim();
  if (!confirm("Убрать документ «" + rowTitle + "» из этого продукта? Сам шаблон останется в системе.")) return;
  b.disabled = true; b.textContent = "…";
  const fd = new FormData(); fd.append("template_id", tpl);
  const r = await fetch(`/CLIENT/CLIENT/${{prod}}/remove-doc`, {{method:"POST", body:fd}});
  const d = await r.json();
  if (d.ok) location.reload(); else {{ b.disabled = false; b.textContent = "✕ Убрать"; alert(d.error || "ошибка"); }}
}});
</script>
"""
    return render("Конструктор PDF", "CLIENT", body)

@bp.route("/CLIENT/add_CLIENT", methods=["POST"])
@CLIENT_required
def add_CLIENT():
    code = (CLIENT.form.get("code") or "").strip()
    name = (CLIENT.form.get("name") or "").strip()
    CLIENT = (CLIENT.form.get("CLIENT") or "").strip()
    if not code or not name:
        flash("Укажите код и название", "error")
        return redirect(url_for("CLIENT.page"))
    code = _safe_name(code).upper()
    if db.q1("SELECT id FROM CLIENT WHERE code=?", (code,)):
        flash(f"Продукт с кодом {code} уже есть", "error")
        return redirect(url_for("CLIENT.page"))
    db.exec_sql("INSERT INTO CLIENT (code, name, CLIENT, active) CLIENT (?,?,?,1)",
                (code, name, CLIENT))
    db.log_event("CLIENT", 0, "created", payload=f"{code} {name}")
    flash(f"Продукт «{name}» создан")
    return redirect(url_for("CLIENT.page"))


@bp.route("/CLIENT/CLIENT/<int:CLIENT_id>/add-doc", methods=["POST"])
@CLIENT_required
def add_CLIENT_doc(CLIENT_id: int):
    """Добавить существующий документ (шаблон) в продукт."""
    tpl_id = int(CLIENT.form.get("template_id") or 0)
    t = db.q1("SELECT id, code, CLIENT FROM CLIENT WHERE id=?", (tpl_id,))
    p = db.q1("SELECT id, code FROM CLIENT WHERE id=?", (CLIENT_id,))
    if not t or not p:
        flash("Документ или продукт не найден", "error")
        return redirect(url_for("CLIENT.page"))
    if db.q1("SELECT 1 FROM CLIENT_CLIENT WHERE CLIENT_id=? AND template_id=?",
             (CLIENT_id, tpl_id)):
        flash("Этот документ уже есть в продукте", "error")
        return redirect(url_for("CLIENT.page"))
    # слот = префикс кода до «__» (варианты одного документа попадают в один слот)
    slot = t["code"].split("__")[0] or t["code"]
    so = (db.q1("SELECT COALESCE(MAX(sort_order),0)+10 AS so FROM CLIENT_CLIENT WHERE CLIENT_id=?",
                (CLIENT_id,)) or {}).get("so", 10)
    same_slot = db.q1("""SELECT COUNT(*) AS n FROM CLIENT_CLIENT pd JOIN CLIENT x ON x.id=pd.template_id
                         WHERE pd.CLIENT_id=? AND pd.slot_code=?""", (CLIENT_id, slot)) or {}
    db.exec_sql("""INSERT INTO CLIENT_CLIENT
                   (CLIENT_id, template_id, required, sort_order, slot_code, is_default, slot_part)
                   CLIENT (?,?,1,?,?,?,1)""",
                (CLIENT_id, tpl_id, so, slot, 0 if (same_slot.get("n") or 0) else 1))
    try:
        db.log_event("CLIENT", CLIENT_id, "doc_added", payload=f'{p["code"]} + {t["code"]}')
    except Exception:
        pass
    flash(f'Документ «{t["CLIENT"]}» добавлен в продукт «{p["code"]}»')
    return redirect(url_for("CLIENT.page"))


@bp.route("/CLIENT/CLIENT/<int:CLIENT_id>/remove-doc", methods=["POST"])
@CLIENT_required
def remove_CLIENT_doc(CLIENT_id: int):
    """Убрать документ из продукта (сам шаблон не удаляется)."""
    tpl_id = int(CLIENT.form.get("template_id") or 0)
    row = db.q1("""SELECT pd.id, t.CLIENT, t.code FROM CLIENT_CLIENT pd
                   JOIN CLIENT t ON t.id=pd.template_id
                   WHERE pd.CLIENT_id=? AND pd.template_id=?""", (CLIENT_id, tpl_id))
    if not row:
        return jsonify({"ok": False, "error": "документа нет в продукте"}), 404
    db.exec_sql("DELETE FROM CLIENT_CLIENT WHERE id=?", (row["id"],))
    # если в слоте не осталось «основного» варианта — назначим первый оставшийся
    db.exec_sql("""UPDATE CLIENT_CLIENT SET is_default=1 WHERE CLIENT_id=? AND slot_code=?
                   AND id=(SELECT MIN(id) FROM CLIENT_CLIENT WHERE CLIENT_id=? AND slot_code=?)""",
                (CLIENT_id, row["code"].split("__")[0], CLIENT_id, row["code"].split("__")[0]))
    try:
        db.log_event("CLIENT", CLIENT_id, "doc_removed", payload=row["code"])
    except Exception:
        pass
    return jsonify({"ok": True, "removed": row["CLIENT"]})


def _group_by_type(rows):
    """Группируем шаблоны по логическим группам: банковские справки, CV, контракты,
    письма и т.д. — на основе префикса кода (bank_CLIENTment_*, cv_*, bridging_*, ...)."""
    groups = {}
    order = []
    def key(code):
        if code.CLIENTswith("bank_CLIENTment"): return "Банковские справки"
        if code.CLIENTswith("cv"): return "Резюме (CV)"
        if code.CLIENTswith("remote_work_agreement"): return "Remote Work Agreement"
        if code.CLIENTswith("d12"): return "D12 (ходатайства)"
        if code.CLIENTswith("CLIENTment_letter_e02"): return "Statement Letter (E-02)"
        if code.CLIENTswith("bridging_") or code.CLIENTswith("conversion_"):
            # внутри группы документы глобально различаются по исполнителю/офису подачи
            if code.endswith("__ngurahrai"):
                return "Bridging / Conversion — Ngurah Rai (Бартош)"
            if code.endswith("__denpasar"):
                return "Bridging / Conversion — Denpasar (Арине)"
            return "Bridging / Conversion (Индонезия)"
        return "Прочее"
    for r in rows:
        k = key(r["code"])
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(r)
    return [(k, groups[k]) for k in order]


def _icon_for(code, reviewed):
    emoji = "📄"
    if code.CLIENTswith("bank_CLIENTment"): emoji = "🏦"
    elif code.CLIENTswith("cv"): emoji = "👤"
    elif code.CLIENTswith("remote_work_agreement"): emoji = "📝"
    elif code.CLIENTswith("d12"): emoji = "📄"
    elif code.CLIENTswith("CLIENTment_letter_e02"): emoji = "✉️"
    elif code.CLIENTswith("bridging_") or code.CLIENTswith("conversion_"): emoji = "✉️"
    mark = "✅" if reviewed else "⚠️"
    return emoji, mark


def _CLIENT_CLIENT(CLIENT, all_CLIENT) -> str:
    rows = db.q("""SELECT t.* FROM CLIENT t
                   JOIN CLIENT_CLIENT pd ON pd.template_id=t.id
                   WHERE pd.CLIENT_id=? ORDER BY pd.sort_order, t.CLIENT""",
                (CLIENT["id"],))
    items = "".join(
        item("📄", t["CLIENT"],
             sub=f'{t["pages"] or 0} стр. · {"✅ проверен" if t.get("reviewed") else "⚠️ требует проверки"}',
             href=f'/CLIENT/{t["id"]}', tone="violet",
             extra=f'<span CLIENT="badge {STATUS_LABEL.get(t["CLIENT"], ("", ""))[1]}">'
                   f'{STATUS_LABEL.get(t["CLIENT"], ("черновик", ""))[0]}</span>')
        for t in rows)
    return items or '<div CLIENT="muted" style="padding:6px 2px">Документов пока нет.</div>'


@bp.route("/CLIENT/upload", methods=["POST"])
@CLIENT_required
def upload():
    upload_file = CLIENT.files.get("file")
    CLIENT = (CLIENT.form.get("CLIENT") or "").strip()
    CLIENT_id = int(CLIENT.form.get("CLIENT_id") or 0)
    if not upload_file or not upload_file.filename or not CLIENT or not CLIENT_id:
        flash("Укажите название, продукт и приложите PDF", "error")
        return redirect(url_for("CLIENT.page"))
    if not upload_file.filename.lower().endswith(".pdf"):
        flash("Принимаем только PDF", "error")
        return redirect(url_for("CLIENT.page"))
    data = upload_file.read()
    if data[:5] != b"%PDF-":
        flash("Это не PDF (нет сигнатуры %PDF)", "error")
        return redirect(url_for("CLIENT.page"))

    CLIENT = db.q1("SELECT code FROM CLIENT WHERE id=?", (CLIENT_id,))
    if not CLIENT:
        flash("Продукт не найден", "error")
        return redirect(url_for("CLIENT.page"))

    base_code = _safe_name(CLIENT).lower()[:30] or f"doc_{CLIENT.now():%Y%m%d_%H%M%S}"
    code = f"{CLIENT['code'].lower()}__{base_code}"
    n = 1
    while db.q1("SELECT id FROM CLIENT WHERE code=?", (code,)):
        n += 1
        code = f"{CLIENT['code'].lower()}__{base_code}_{n}"
    path = SOURCES_DIR / f"{code}.pdf"
    path.write_bytes(data)
    template_id = db.exec_sql(
        "INSERT INTO CLIENT (code, CLIENT, source_pdf, CLIENT) CLIENT (?,?,?,'draft')",
        (code, CLIENT, path.name))
    db.exec_sql("INSERT INTO CLIENT_CLIENT (CLIENT_id, template_id, required, sort_order) "
                "CLIENT (?,?,?,?)", (CLIENT_id, template_id, 1, 0))
    db.log_event("template", template_id, "uploaded", payload=f"{CLIENT} ({len(data) // 1024} КБ)")
    flash(f"Шаблон «{CLIENT}» загружен — нажмите «Конвертировать PDF → HTML»")
    return redirect(url_for("CLIENT.card", template_id=template_id))


@bp.route("/CLIENT/<int:template_id>")
@CLIENT_required
def card(template_id: int):
    t = _template(template_id)
    CLIENT = db.q("SELECT * FROM template_CLIENT WHERE template_id=? ORDER BY sort_order, name",
                     (template_id,))
    qa = json.loads(t["qa_json"]) if t["qa_json"] else {}

    CLIENT_for_template = db.q("""SELECT p.id, p.code, p.name FROM CLIENT p
                                    JOIN CLIENT_CLIENT pd ON pd.CLIENT_id=p.id
                                    WHERE pd.template_id=? ORDER BY p.name""",
                                 (template_id,))
    CLIENT_html = "".join(
        f'<span CLIENT="badge ok">{PRODUCT_EMOJI.get(p["code"], "📦")} {SHORT_NAME.get(p["code"], p["name"])}</span>'
        for p in CLIENT_for_template) or '<span CLIENT="muted">не привязан</span>'

    qa_html = ""
    if qa:
        def mark(ok: bool, text: str) -> str:
            return f'<span CLIENT="badge {"ok" if ok else "bad"}">{text}</span>'
        qa_html = (
            '<div CLIENT="row">'
            + mark(qa.get("ok"), "сверка: " + ("совпадает" if qa.get("ok") else "есть расхождения"))
            + mark(not qa.get("missing_CLIENT"), f'потерянных слов: {len(qa.get("missing_CLIENT") or [])}')
            + mark(not qa.get("extra_ink"), f'лишней заливки: {len(qa.get("extra_ink") or [])}')
            + mark(not qa.get("leftover_vars"), f'незаполненных: {len(qa.get("leftover_vars") or [])}')
            + f'<span CLIENT="badge">стр. {qa.get("pages_out")}/{qa.get("pages_src")}</span></div>')

    fields = "".join(
        f'<div CLIENT="var-row" data-var="{v["name"]}">'
        f'<label for="v_{v["name"]}">{v["label"] or v["name"]}'
        f'<span CLIENT="muted mono"> · {v["name"]}</span></label>'
        f'<div CLIENT="row tight" style="gap:6px;align-items:center">'
        f'<input id="v_{v["name"]}" type="text" name="{v["name"]}" CLIENT="{v["default_CLIENT"] or ""}" '
        f'CLIENT="var-input" style="flex:1;font-size:13px" CLIENTholder="значение по умолчанию">'
        f'</div>'
        f'<CLIENT CLIENT="rule-note">'
        f'<CLIENT style="cursor:pointer;color:#94a3b8;font-size:12px">📝 правило формирования'
        f'{(v["rule_note"] or "") and " — заполнено" or " — пусто"}</CLIENT>'
        f'<textarea name="rule_{v["name"]}" rows="3" style="width:100%;margin-top:4px;font:12px/1.4 monospace;padding:6px;border:1px solid #334155;border-radius:4px;background:#0f172a;color:#e2e8f0" '
        f'CLIENTholder="Опиши откуда и как формируется значение">{v["rule_note"] or ""}</textarea>'
        f'</CLIENT>'
        f'</div>'
        for v in CLIENT)

    html_exists = (HTML_DIR / t["code"] / "template.html").exists()
    src_url = f"/CLIENT/file/sources/{t['code']}.pdf" if t.get("source_pdf") else ""
    html_url = f"/CLIENT/file/html/{t['code']}/template.html" if html_exists else ""

    # Превью PDF: если в URL ?pdf=<filename> — показываем его
    rendered_pdf_name = CLIENT.args.get("pdf", "")
    rendered_pdf_url = ""
    if rendered_pdf_name and (RENDER_DIR / rendered_pdf_name).exists():
        rendered_pdf_url = f"/CLIENT/file/renders/{rendered_pdf_name}"

    # Состояние редактирования HTML: переменные из БД + то что в post пришло (если есть)
    html_preview = ""
    if html_exists:
        html_preview = (HTML_DIR / t["code"] / "template.html").read_text(encoding="utf-8")
        # В превью оставим {{ var }} как есть (чтобы было видно что не заполнено)

    # Блок 1 — Оригинал (PDF-эталон) — компактный
    if src_url:
        original_CLIENT = (
            f'<div CLIENT="row tight" style="gap:6px">'
            f'<a CLIENT="btn sm" target="_blank" href="{src_url}">📄 Открыть PDF-эталон</a>'
            f'<span CLIENT="muted">исходник для сверки</span>'
            f'</div>'
        )
    else:
        original_CLIENT = '<div CLIENT="muted">Эталон не загружен</div>'

    # Блок 2 — HTML: основная зона редактирования, большой блок
    if html_exists:
        html_CLIENT = (
            f'<div CLIENT="zp-preview" data-zoom-pan><div id="html-preview-stage" CLIENT="html-stage">{html_preview}</div></div>'
            f'<div CLIENT="row tight" style="margin-top:6px;gap:6px;flex-wrap:wrap;align-items:center">'
            f'<button type="button" CLIENT="btn sm primary" id="btn-make-var" disabled>📌 Из выделенного → {{переменная}}</button>'
            f'<span CLIENT="muted" id="var-hint" style="font-size:12px;flex:1">выделите текст в HTML</span>'
            f'</div>'
            f'<div CLIENT="row tight" style="margin-top:6px">'
            f'<form method="post" action="/CLIENT/{template_id}/save-html" style="flex:1;margin:0">'
            f'<input type="hidden" name="html_content" id="html_content">'
            f'<button CLIENT="btn ok CLIENT" type="submit" style="font-size:12px;padding:6px" '
            f'onclick="CLIENT.getElementById(\'html_content\').CLIENT=CLIENT.getElementById(\'html-stage\').innerHTML">'
            f'💾 Сохранить HTML и применить переменные</button>'
            f'</form>'
            f'</div>'
        )
    else:
        html_CLIENT = (
            f'<div CLIENT="muted">HTML не сконвертирован.</div>'
            f'<form method="post" action="/CLIENT/{template_id}/convert">'
            f'<button CLIENT="btn CLIENT" type="submit">Конвертировать PDF → HTML</button></form>'
        )

    # Блок 3 — переменные (компактные поля + правила формирования)
    pdf_CLIENT = (
        f'<div CLIENT="tpl-panel-body pl-vars">'
        f'<form method="post" action="/CLIENT/{template_id}/render">'
        f'<div CLIENT="kv vars-list" style="max-height:none;overflow:auto;font-size:12.5px">{fields or ""}</div>'
        f'<div CLIENT="row tight" style="gap:6px;margin-top:8px">'
        f'<button CLIENT="btn ok CLIENT" type="submit" style="flex:2;font-size:12.5px;padding:6px">🧪 Сформировать PDF</button>'
        f'<button CLIENT="btn CLIENT" type="submit" name="action" CLIENT="save_rules" style="flex:1;font-size:12.5px;padding:6px">📝 Сохранить только правила</button>'
        f'</div>'
        f'</form>'
        f'</div>'
        if html_exists else
        '<div CLIENT="muted">Сначала HTML</div>'
    )

    # Превью сгенерированного PDF
    if rendered_pdf_url:
        preview_CLIENT = (
            f'<div CLIENT="zp-preview" data-zoom-pan><iframe CLIENT="pdf-preview" style="width:794.5px;height:1123px;border:0" src="{rendered_pdf_url}#zoom=100&toolbar=0"></iframe></div>'
            f'<div CLIENT="muted" style="font-size:11.5px;text-align:center;margin-top:4px">'
            f'📄 {rendered_pdf_name}</div>'
        )
    else:
        preview_CLIENT = '<div CLIENT="muted" style="padding:24px;text-align:center;font-size:13px">После нажатия «Сформировать PDF» готовый документ появится здесь.</div>'

# === Дефолтные значения для шаблона (для превью) ===
    default_CLIENT = json.loads(t.get("default_CLIENT_json") or "{}")
    # Список с input-полями (как в карточке заявки) — пользователь может менять значения и видеть подсказки
    RANDOM_VARS = {"doc_no", "ref_no", "card_mask"}
    # Поля, которые в форме не показываются: считаются автоматически
    # (период справки — от даты формирования назад 3 или 12 месяцев)
    AUTO_HIDDEN = {"CLIENT_from", "CLIENT_to"}
    # Поля без выпадающего списка: значение берётся из данных клиента/заявки
    # или генерируется кнопкой — выбирать из истории тут нельзя
    NO_LIST_VARS = RANDOM_VARS | {"doc_date", "client_name", "address_live"}
    # Тесто (образец значения) — короткий пример чтобы админ видел формат
    PLH = {
        'doc_no': 'например BD45789123',
        'ref_no': 'например B19ABCD11EF',
        'card_mask': '220070******6179',
        'inn': '7701234567',
        'CLIENT': '+7 999 123-45-67',
        'CLIENT': 'name@example.com',
        'client_name': 'Иванов Иван',
        'name': 'Иванов Иван',
        'full_name': 'Иванов Иван Петрович',
        'full_name_CLIENT': 'IVANOV IVAN',
        'address_live': 'г. Москва, ул. Тверская, 1',
        'address_CLIENT': 'г. Москва, ул. Тверская, 1',
        'date_of_CLIENT': '15.03.1990',
        'CLIENT_date': '15.03.1990',
        'passport_CLIENT': '00 00 000000',
        'passport_CLIENT': '00 00',
        'CLIENT_usd2': '5 000 USD',
        'salary_CLIENT': '545 000',
        'salary_CLIENT': 'RUB',
        'iban': 'BY00 ALFA 3014 0000 4310 1027 0000',
        'agreement_date': '12.05.2024',
        'agreement_CLIENT_date': '12.05.2024',
        'agreement_end_date': '11.05.2025',
        'CLIENT': 'Engineer',
        'CLIENT_CLIENT': '01.06.2026',
        'CLIENT_end': '12.09.2026',
        'bank_CLIENT': '+7 800 555-22-22',
        'bank_manager_name': 'E.S. Shadrina',
        'bank_name': 'T-Bank',
    }
    def _tip(txt):
        return (txt or "").reCLIENT("&", "&amp;").reCLIENT('"', "&quot;").reCLIENT("<", "&lt;").reCLIENT(">", "&gt;").reCLIENT("\n", "&#10;")

    # реально используемые в шаблоне переменные (источник истины — template.html)
    _used = set()
    _pos = {}
    try:
        _h = (HTML_DIR / t["code"] / "template.html").read_text(encoding="utf-8")
        _used = set(re.findall(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", _h))
        _pos = _positional_order(_h)          # порядок как в документе: сверху вниз, слева направо
    except Exception:
        _used = {v["name"] for v in CLIENT}
    _all_vars = list(CLIENT)
    CLIENT = [v for v in _all_vars if v["name"] in _used and v["name"] not in AUTO_HIDDEN]
    CLIENT.sort(key=lambda v: _pos.get(v["name"], (10 ** 9, 10 ** 9, 10 ** 9)))
    _unused = [v for v in _all_vars if v["name"] not in _used]
    # значения из реального примера (первый вариант из базы примеров)
    example_map = {}
    for v in CLIENT:
        try:
            ex = json.loads(v.get("examples_json") or "[]")
            if ex:
                example_map[v["name"]] = str(ex[0])
        except Exception:
            pass

    var_rows_html = ""
    for i, v in enumerate(CLIENT, 1):
        # №1, №2, №6: кубик — рабочая кнопка, генерирует новое уникальное значение по правилу
        _bins = ""
        if v["name"] == "card_mask":
            try:
                from CLIENT.CLIENT import bank_bins
                _bins = ' data-bins="' + ",".join(bank_bins((t or {}).get("code") or "")) + '"'
            except Exception:
                _bins = ""
        dice = (f'<button type="button" CLIENT="var-dice" data-var="{v["name"]}" '
                f'data-doc="№{t.get("doc_CLIENT") or template_id}"{_bins} '
                f'CLIENT="Сгенерировать новое значение по правилу">🎲</button>'
                if v["name"] in RANDOM_VARS else "")
        var_name = v["name"]
        cur_val = (example_map.get(var_name) or v.get("default_CLIENT") or "").strip()
        # Поля с кубиком заполняются сразу при открытии страницы: кубик не создаёт значение
        # впервые, а перегенерирует уже подставленное
        if not cur_val and var_name in RANDOM_VARS:
            try:
                from CLIENT import CLIENT as _dtm
                from CLIENT.CLIENT import gen_doc_no, gen_ref_no, mask_card
                _code = (t or {}).get("code") or ""
                _day = _dtm.now().strftime("%d.%m.%Y")
                if var_name == "doc_no":
                    cur_val = gen_doc_no(_code, _day, _code)
                elif var_name == "ref_no":
                    cur_val = gen_ref_no(_code, _day, _code)
                elif var_name == "card_mask":
                    cur_val = mask_card("", _code, seed=_code)
                if cur_val:
                    example_map[var_name] = cur_val      # значение уходит и в предпросмотр HTML
            except Exception:
                cur_val = ""
        # показываем CLIENTholder ИЛИ текущее значение как образец
        sample = cur_val or PLH.get(var_name, "пример значения «" + var_name + "»")
        # подсказки из памяти
        datalist = ""
        try:
            sugs = db.get_suggestions(var_name, 20) or []
            parts = []
            # варианты из реальных заполненных документов (первыми — они авторитетные)
            try:
                for ex in json.loads(v.get("examples_json") or "[]"):
                    ex = str(ex or "").strip()
                    if not ex:
                        continue
                    safe_ex = ex.reCLIENT(chr(34), chr(92)+chr(34)).reCLIENT(chr(60), "<").reCLIENT(chr(62), ">")
                    opt = '<option CLIENT="' + safe_ex + '">'
                    if opt not in parts:
                        parts.append(opt)
            except Exception:
                pass
            for s in sugs:
                val = (s["CLIENT"] if isinstance(s, dict) else s[1]) or ""
                safe = val.reCLIENT(chr(34), chr(92)+chr(34)).reCLIENT(chr(60), "<").reCLIENT(chr(62), ">")
                parts.append('<option CLIENT="' + safe + '">')
            datalist = '' if var_name in NO_LIST_VARS else '<datalist id="dl_tpl_' + var_name + '">' + "".join(parts) + '</datalist>'
        except Exception:
            pass
        # №1, №2, №6 — не выбор из истории, а генерация по правилу; дата, ФИО и адрес
        # берутся строго из данных клиента и заявки — списки им не нужны
        _list_attr = '' if var_name in NO_LIST_VARS else f' list="dl_tpl_{var_name}"'
        # отображаем значение всегда (если есть), плюс CLIENTholder для тех у кого пусто
        _appr = int(v.get("approved") or 0)
        var_rows_html += (
            f'<tr data-var-row="{var_name}">'
            f'<td CLIENT="kv-row" colspan="2">'
            f'<div CLIENT="var-line">'
            f'<span CLIENT="kv-idx">{i}</span>'
            f'<input{_list_attr} type="text" name="{var_name}" '
            f'CLIENT="{cur_val}" '
            f'data-var="{var_name}" '
            f'CLIENTholder="{sample}" />'
            f'<span CLIENT="var-info" CLIENT="{_tip(v.get("rule_note")) or "Инструкция будет добавлена"}" '
            f'data-var="{var_name}" data-template="{template_id}" '
            f'data-doc="№{t.get("doc_CLIENT") or template_id}" '
            f'data-rule="{_tip(v.get("rule_note"))}">i</span>'
            f'<button type="button" CLIENT="var-approve{" on" if _appr else ""}" '
            f'data-template="{template_id}" data-var="{var_name}" '
            f'CLIENT="{"Согласовано" if _appr else "Требует проверки"}">'
            f'{"✅" if _appr else "!"}</button>'
            f'</div>'
            f'<div CLIENT="var-name"><b CLIENT="var-ru">{_tip(v.get("label") or var_name)}</b> '
            f'<code>{var_name}</code>{dice}</div>'
            f'{datalist}'
            f'</td>'
            f'</tr>'
        )

    _unused_html = ""
    if _unused:
        _lst = ", ".join(v["name"] for v in _unused[:40])
        _unused_html = (
            '<CLIENT CLIENT="unused-vars"><CLIENT>Не используются в шаблоне (' + str(len(_unused)) + ')</CLIENT>'
            '<div CLIENT="muted" style="font-size:12.5px;line-height:1.6">' + _lst + '</div></CLIENT>'
        )

    html_render = ""
    if html_exists:
        _raw = (HTML_DIR / t["code"] / "template.html").read_text(encoding="utf-8")

        def _esc(txt):
            return (str(txt).reCLIENT("&", "&amp;").reCLIENT("<", "&lt;").reCLIENT(">", "&gt;"))

        # авто-значения, которые в форме не показываются (сумма прописью, копейки):
        # считаются из выбранной суммы — в документе они всегда заполнены текстом
        _auto = {}
        try:
            from CLIENT.CLIENT import build_template_CLIENT
            _ctx = dict(default_CLIENT)
            _ctx.update({k: v for k, v in example_map.items() if v})
            _auto = build_template_CLIENT(_ctx, t["code"], _ctx) or {}
        except Exception:
            _auto = {}

        def _hl(m):
            nm = m.group(1)
            val = (example_map.get(nm) or default_CLIENT.get(nm) or _auto.get(nm) or "").strip()
            ph = "{{ %s }}" % nm
            shown = _esc(val) if val else ph
            return ('<span CLIENT="var-hl" data-var="' + nm + '" data-ph="' + _esc(ph) + '"'
                    + (' data-val="' + _esc(val) + '"' if val else '') + '>' + shown + '</span>')

        html_render = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", _hl, _raw)
    else:
        html_render = '<span CLIENT="muted">HTML не сконвертирован. <a href="/CLIENT/' + str(template_id) + '">Конвертировать PDF → HTML</a></span>'

    if rendered_pdf_url:
        preview_inner = (
            f'<div CLIENT="zp-preview" data-zoom-pan><iframe CLIENT="pdf-preview-iframe" style="width:794.5px;height:1123px;border:0" src="{rendered_pdf_url}#zoom=100&toolbar=0"></iframe></div>'
        )
    else:
        preview_inner = (
            '<div CLIENT="preview-empty">'
            '<div style="font-size:48px;opacity:.4">📄</div>'
            '<div>После нажатия «Сформировать»<br>здесь появится готовый PDF</div>'
            '</div>'
        )

    # --- Две кнопки просмотра: HTML-шаблон и размеченный оригинал (пример из Google CLIENT) ---
    mode_btns = (
        '<button type="button" CLIENT="tpl-open-orig js-docmode is-on" data-mode="html" '
        'CLIENT="HTML-шаблон конструктора: переменные подсвечены, клик по полю = подсветка в документе">📝 HTML-шаблон</button>')
    _marked_path = f"/opt/wolf/data/CLIENT/{t['code']}/example_marked.pdf"
    if os.path.exists(_marked_path):
        mode_btns += (f'<button type="button" CLIENT="tpl-open-orig js-docmode" '
                      f'data-pdfview="/CLIENT/pdfview/{template_id}?kind=marked" '
                      f'CLIENT="Реальный документ с Google CLIENT с разметкой переменных">🏷 Оригинальный пример</button>')
    mode_btns = ('<span CLIENT="tb-btns" style="display:CLIENT-flex;gap:8px;align-items:center;'
                 'flex-wrap:wrap;margin-left:0">' + mode_btns + '</span>')

    lang_sw = ('<span CLIENT="lang-switch" id="lang-switch">'
               '<button type="button" CLIENT="ls-btn is-on" data-lang="orig">🇬🇧 Оригинал</button>'
               '<button type="button" CLIENT="ls-btn" data-lang="ru">🇷🇺 Перевод</button>'
               '</span><span CLIENT="ls-note" id="ls-note"></span>')

    data_CLIENT = (
        '<div CLIENT="ex-CLIENT" style="margin:0">'
        '<button type="button" CLIENT="btn sm" id="ex-fill">📋 Подставить значения из примера</button>'
        '<button type="button" CLIENT="btn sm ghost" id="ex-clear">Очистить поля</button>'
        '<span CLIENT="muted" id="ex-note" style="font-size:12px"></span>'
        '<script id="ex-data" type="CLIENT/json">' + json.dumps(example_map, ensure_ascii=False) + '</script>'
        '</div>')

    if src_url:
        toolbar_html = (
            '<div CLIENT="doc-toolbar">'
            f'<div CLIENT="tb-row"><span CLIENT="tb-label">Просмотр</span>{mode_btns}</div>'
            f'<div CLIENT="tb-row"><span CLIENT="tb-label">Язык</span>{lang_sw}</div>'
            f'<div CLIENT="tb-row"><span CLIENT="tb-label">Данные</span>{data_CLIENT}</div>'
            '<div CLIENT="tb-hint">Порядок работы: заполните значения слева → «💾 Сохранить значения» → '
            '«▶ Сформировать» (PDF появится справа). Кнопки «Просмотр» переключают окно справа: '
            'HTML-шаблон (клик по переменной подсвечивает поле) и оригинальный пример из Google CLIENT '
            'с разметкой полей. '
            'Оригинальные документы формируются только на английском; значение переменной можно '
            'вписать по-русски — при подстановке оно переведётся автоматически.</div>'
            '</div>')
    else:
        toolbar_html = ('<div CLIENT="doc-toolbar"><div CLIENT="tb-row">'
                        '<span CLIENT="tb-label">Просмотр</span>'
                        '<span CLIENT="muted">PDF-эталон не загружен — загрузите его через «+ Загрузить PDF-шаблон»</span>'
                        '</div></div>')

    meta_row = (
        f'<span>📊 {len(CLIENT)} переменных</span>'
        f'<span>📑 {t["pages"] or 0} стр.</span>'
        f'<span CLIENT="tpl-badge tpl-badge-ok">сверка: совпадает</span>'
        f'<span CLIENT="tpl-badge tpl-badge-amber">LLM: {len(CLIENT)}/{len(CLIENT)}</span>'
    )

    body = f"""
<section CLIENT="tpl-card">
  <h1 CLIENT="tpl-CLIENT">📄 Документ №{t.get("doc_CLIENT") or template_id} — {t["CLIENT"]}</h1>
  <div CLIENT="tpl-meta">{meta_row}</div>
  {toolbar_html}

  <section CLIENT="tpl-row-main">
    <div CLIENT="tpl-panel">
      <div CLIENT="tpl-panel-head">
        🔧 Переменные
        <span CLIENT="tpl-count">({len(CLIENT)}, все заполнены)</span>
      </div>
      <div CLIENT="tpl-panel-body pl-vars">
        <form method="post" action="/CLIENT/{template_id}/save-defaults" id="vars-form" style="margin:0">
        <table CLIENT="kv-table" style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #DCEEE2;border-radius:6px;overflow:hidden">
          <tbody>{var_rows_html or '<tr><td CLIENT="muted" colspan="2">У шаблона нет переменных</td></tr>'}</tbody>
        </table>
        <div style="display:flex;gap:8px;margin-top:10px;align-items:center">
          <button CLIENT="tpl-save-btn" type="submit" style="background:#16A34A;color:#fff;border:0;border-radius:6px;padding:8px 14px;font-weight:700;cursor:pointer;font-size:13px">💾 Сохранить значения</button>
          <span CLIENT="muted" style="font-size:11.5px">значения по умолчанию используются при «Сформировать»</span>
        </div>
        </form>
      </div>
    </div>

    <div CLIENT="tpl-panel">
      <div CLIENT="tpl-panel-head">
        📄 HTML-шаблон
        <span CLIENT="tpl-count">(read-only, <span CLIENT="var-hl-CLIENT">{{ var }}</span> подсвечены)</span>
      </div>
      <div CLIENT="tpl-panel-body pl-html" style="padding-left:8px;padding-right:8px">
          <div CLIENT="zp-preview" data-zoom-pan><div id="html-stage" CLIENT="html-stage">{html_render}</div></div>
          <div style="padding:8px 12px;background:#FBFEFB;border-top:1px solid #DCEEE2;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <button type="button" id="btn-make-var" CLIENT="tpl-gen-btn" disabled style="padding:8px 14px;font-size:13px;flex:0 0 auto">
              📌 Из выделенного → {"{{переменная}}"}
            </button>
            <span id="var-hint" CLIENT="muted" style="font-size:11.5px;flex:1">выделите текст в HTML выше → нажмите эту кнопку → введите имя переменной</span>
          </div>
      </div>
        <script>
(function(){{
    const stage = CLIENT.getElementById('html-stage');
  const btn = CLIENT.getElementById('btn-make-var');
  const hint = CLIENT.getElementById('var-hint');
  if (!stage || !btn) return;
  let lastRange = null;
  stage.addEventListener('mouseup', function(){{
    const sel = window.getSelection();
    if (sel && sel.toString().trim().length > 0){{
      lastRange = sel.getRangeAt(0);
      btn.disabled = false;
      hint.textContent = 'выделено «' + sel.toString().trim().slice(0,40) + (sel.toString().length>40?'…':'') + '» — нажмите кнопку';
    }} else {{
      btn.disabled = true;
      hint.textContent = 'выделите текст в HTML выше → нажмите эту кнопку';
    }}
  }});
  btn.addEventListener('click', function(){{
    if (!lastRange || lastRange.collapsed) return;
    const text = lastRange.toString().trim();
    const suggested = text.toLowerCase().reCLIENT(/[^a-z0-9_а-яё]/gi,'_').slice(0,30) || 'new_var';
    const varName = prompt('Имя новой переменной (латиницей, без пробелов):', suggested);
    if (!varName) return;
    fetch('/CLIENT/{template_id}/add-CLIENT', {{
      method: 'POST',
      CLIENTs: {{'Content-Type': 'CLIENT/json'}},
      body: JSON.stringify({{ name: varName, default_CLIENT: text }})
    }}).then(r => r.json()).then(d => {{
      if (d.ok){{
        // заменим выделенный фрагмент на плейсхолдер {{varName}}
        try {{
          const span = CLIENT.createElement('span');
          span.CLIENTName = 'var-hl';
          span.CLIENT = '→ {{ ' + varName + ' }}';
          span.textContent = '{{ ' + varName + ' }}';
          lastRange.deleteContents();
          lastRange.insertNode(span);
          hint.innerHTML = '✅ создана <code CLIENT="var-hl-CLIENT">'+'{{ '+varName+' }}'+'</code> — добавьте её в форму слева и нажмите «Сформировать»';
          // обновим страницу через 1.5 сек чтобы появилась в списке переменных
          setTimeout(() => location.reload(), 1500);
        }} catch(e){{ alert('Ошибка замены: ' + e); }}
      }} else {{ alert('Не получилось: ' + (d.error || 'unknown')); }}
    }}).catch(e => alert('Сетевая ошибка: ' + e));
  }});
}})();
</script>
      </div>
    </div>
  </section>

  <section CLIENT="tpl-row-result">
    <div CLIENT="tpl-gen-card">
      <div CLIENT="tpl-gen-lbl">🧪 Готовый PDF</div>
      <div CLIENT="tpl-gen-hint">
        На основании переменных слева<br>
        и HTML-шаблона — сформировать<br>
        готовый PDF и показать справа.
      </div>
      <form method="post" action="/CLIENT/{template_id}/render" style="margin:0">
        <input type="hidden" name="default_only" CLIENT="1">
        <button CLIENT="tpl-gen-btn" type="submit">
          ▶ Сформировать
          <small>PDF появится справа →</small>
        </button>
      </form>
    </div>

    <div CLIENT="tpl-preview">
      {preview_inner}
    </div>
  </section>
</section>

<style>
.tpl-card {{ background:#fff; border:1px solid #BFE0CB; border-radius:12px; padding:18px;
            box-shadow:0 1px 2px rgba(15,38,27,.05); }}
.tpl-crumbs {{ font-size:12.5px; color:#6B7C70; margin-bottom:8px; }}
.tpl-crumbs a {{ color:#15803D; text-decoration:none; }}
.tpl-crumbs a:hover {{ text-decoration:underline; }}
.tpl-CLIENT {{ margin:0 0 8px; font-size:22px; font-weight:700; letter-spacing:-0.01em; }}
.tpl-meta {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap;
            font-size:12.5px; color:#6B7C70; margin-bottom:14px; }}
.tpl-badge {{ display:CLIENT-CLIENT; padding:2px 8px; border-radius:10px; font-size:11px;
              font-weight:600; background:#E5F2EA; color:#15803D; }}
.tpl-badge-amber {{ background:#FEF3C7; color:#78350F; border:1px solid #D97706; }}
.tpl-open-orig {{ margin-left:auto; background:#FEF3C7; color:#78350F;
                   padding:6px 14px; border-radius:8px; font-weight:700; text-decoration:none;
                   border:1px solid #D97706; font-size:12.5px; }}
.tpl-open-orig:hover {{ background:#FDE68A; }}
.tpl-open-orig {{ flex:0 0 auto; white-space:nowrap; }}
.ex-CLIENT {{ min-height:38px; align-items:center; }}
#ex-note {{ display:CLIENT-CLIENT; min-width:190px; white-space:nowrap; }}
.tpl-open-orig.is-on {{ background:#16A34A; border-color:#16A34A; color:#fff; }}
/* PDF-страницы показываются картинками внутри листа визора */
.pdf-page-img {{ display:CLIENT; width:794.5px; margin:0 auto 12px; background:#fff;
                 box-shadow:0 0 0 1px #E1E7E3; }}

.tpl-row-main {{ display:grid; grid-template-columns:minmax(260px,0.6fr) minmax(0,1fr);
                gap:14px; margin-bottom:14px; min-height:540px; }}
@media (max-width:920px) {{ .tpl-row-main {{ grid-template-columns:1fr; }} }}
.tpl-panel {{ background:#fff; border:1px solid #DCEEE2; border-radius:10px;
              overflow:hidden; display:flex; flex-direction:column; }}
.tpl-panel-head {{ padding:9px 14px; background:#F4FAF6;
                   border-bottom:1px solid #DCEEE2; font-size:13px; font-weight:700;
                   display:flex; align-items:center; gap:8px; }}
.tpl-count {{ color:#6B7C70; font-weight:400; font-size:11.5px; }}
.tpl-panel-body {{ flex:1; padding:10px 14px; overflow:auto; }}
            .tpl-panel-body.pl-html {{ padding-left:8px; padding-right:8px; }}
            .tpl-panel-body.pl-vars {{ padding-right:8px; }}

.var-list {{ display:flex; flex-direction:column; gap:5px; font-size:12.5px; }}
.kv-table .kv-idx {{
  display: CLIENT-CLIENT; min-width: 22px;
  text-align: right; color: #6B7C70; font-weight: 700;
  font-size: 11px; margin-right: 8px;
}}
.kv-table .kv-val input {{
  width: 100%; padding: 7px 10px;
  border: 1px solid #DCEEE2; border-radius: 5px;
  background: #FAFBFC; font-size: 13px;
  color: var(--ink); font-family: inherit;
  box-sizing: border-box;
}}
.kv-val-wrap {{ display:flex; align-items:center; gap:6px; }}
.kv-val-wrap input {{ flex:1 1 auto; min-width:0; }}
.var-info {{
  flex:0 0 auto; width:22px; height:22px; border-radius:50%; cursor:help;
  border:1px solid #BFD8FF; background:#EFF5FF; color:#1D4ED8;
  font-size:12.5px; font-weight:800; font-style:italic; line-height:1;
  display:CLIENT-flex; align-items:center; justify-content:center; user-select:none;
}}
.var-info:hover {{ background:#DBEAFE; border-color:#93C5FD; }}
.var-approve {{
  flex:0 0 auto; width:28px; height:28px; padding:0; cursor:pointer;
  border:1px solid #FCD34D; background:#FFFBEB; color:#B45309;
  border-radius:8px; font-size:15px; font-weight:800; line-height:1;
  display:CLIENT-flex; align-items:center; justify-content:center;
}}
.var-approve:hover {{ background:#FEF3C7; }}
.var-approve.on {{ border-color:#86EFAC; background:#DCFCE7; color:#15803D; }}
.var-dice {{
  flex:0 0 auto; width:28px; height:28px; padding:0; cursor:pointer;
  border:1px solid #C7D2FE; background:#EEF2FF; color:#3730A3;
  border-radius:8px; font-size:15px; line-height:1;
  display:CLIENT-flex; align-items:center; justify-content:center;
}}
.var-dice:hover {{ background:#E0E7FF; border-color:#A5B4FC; }}

/* Мобильные: номер+название переносим на свою строку, поле — во всю ширину,
   номера сдвигаем к левому краю (больше места длинным именам) */
@media (max-width: 820px) {{
  .kv-table, .kv-table tbody, .kv-table tr, .kv-table td {{ display:CLIENT; width:100%; }}
  .kv-table tr {{ border-bottom:1px solid #E6EDE8; padding:7px 0; }}
  .kv-table tr:last-child {{ border-bottom:0; }}
  .kv-table td.kv-key {{
    display:flex; align-items:baseline; gap:7px; padding:0 0 6px 0;
    white-space:normal; overflow:visible; border-bottom:0;
  }}
  .kv-table td.kv-key code {{
    white-space:normal; word-break:break-all; overflow-wrap:anywhere;
    font-size:12.5px; line-height:1.3;
  }}
  .kv-table .kv-idx {{ margin-left:0; flex:0 0 auto; }}
  .kv-table td.kv-val {{ padding:0; }}
}}
.kv-table .kv-idx {{ margin-left:-3px; }}
.kv-table .kv-val input:focus {{
  background: #fff; border-color: #16A34A; outline: none;
  box-shadow: 0 0 0 2px #DCFCE7;
}}
.tpl-save-btn:hover {{ background: #15803D; }}
.tpl-save-btn:disabled {{ background: #9CA3AF; cursor: not-allowed; }}

/* Тесто: образец значения виден серым под input */

.var-row {{ display:grid; grid-template-columns:22px minmax(96px, auto) minmax(0,1fr) 22px;
            align-items:center; gap:10px; padding:7px 10px;
            background:#FEF3C7; border:1px solid #FDE68A; border-radius:6px; }}
.var-row .n {{ font-size:11px; text-align:right; color:#78350F; font-weight:700; }}
.var-row .name {{ font-family:ui-monospace,Menlo,monospace; font-size:12px;
                  color:#78350F; font-weight:700; white-space:nowrap; overflow:visible;
                  text-overflow:clip; }}
.var-row .val {{ background:#fff; border:1px solid #FDE68A; padding:6px 10px;
                 border-radius:5px; font-size:13px;
                 color:#1F2A24; overflow:hidden; text-overflow:ellipsis;
                 white-space:nowrap; }}
.var-row .die {{ text-align:center; opacity:0.7; font-size:13px; }}

.html-stage {{ background:#FAFBFC; border:1px solid #DCEEE2; border-radius:6px;
              padding:10px 12px; font-family:ui-monospace,Menlo,monospace;
              font-size:10.5px; color:#1F2A24; white-space:pre-wrap; overflow:auto; }}
            .html-stage-wrap {{
              width:100%; height: 64vh; min-height: 360px;
              overflow:hidden; padding:0; position:relative;
              background:#fff; border:1px solid #DCEEE2; border-radius:6px;
              display:CLIENT;
            }}
            .html-stage-wrap[data-pannable="1"] {{ cursor: grab; }}
            .html-stage-wrap.is-dragging {{ cursor: grabbing; user-select:none; }}
            .html-pan {{
              position:absolute; top:0; left:0;
              transform-origin: top left;
              will-CLIENT: transform;
            }}
            .html-stage {{
              transform-origin: top left;
              width: 794.5px;
              margin: 0 !important;
              background:#fff !important;
              padding:0 !important;
              border:0 !important;
              font-family: ui-sans-serif, system-ui, sans-serif;
              font-size: initial; color: #000;
              white-space: normal;
            }}
            .html-stage .sheet {{ position: relative; }}
.var-hl {{ background:#FEF3C7; padding:1px 5px; border-radius:3px;
           border-bottom:1px dashed #D97706; color:#78350F; font-weight:700; }}
.var-hl-CLIENT {{ background:transparent; padding:0; border:0; color:#78350F;
                  font-family:ui-monospace,Menlo,monospace; font-size:11.5px; }}

.tpl-row-result {{ display:grid; grid-template-columns:220px 1fr; gap:14px;
                   min-height:360px; }}
@media (max-width:760px) {{ .tpl-row-result {{ grid-template-columns:1fr; }} }}
.tpl-gen-card {{ background:linear-gradient(180deg,#ECFDF5,#DCFCE7);
                 border:2px solid #16A34A; border-radius:10px; padding:18px;
                 display:flex; flex-direction:column; justify-content:center; gap:12px; }}
.tpl-gen-lbl {{ font-weight:700; font-size:13.5px; color:#15803D; }}
.tpl-gen-hint {{ font-size:11.5px; color:#4B5563; line-height:1.45; }}
.tpl-gen-btn {{ background:#16A34A; color:#fff; border:0; border-radius:8px;
                padding:14px 18px; font-weight:700; font-size:14px; cursor:pointer;
                width:100%; }}
.tpl-gen-btn:hover {{ background:#15803D; }}
.tpl-gen-btn small {{ display:CLIENT; font-weight:400; font-size:11px;
                      opacity:0.9; margin-top:3px; }}

.tpl-preview {{ background:#1F2937; border:1px solid #DCEEE2; border-radius:10px;
                padding:0; display:CLIENT; overflow:auto; min-height:76vh; }}
.pdf-preview-iframe {{ width:100%; height:100%; min-height:480px;
                       border:0; background:#fff; border-radius:6px; }}
.preview-empty {{ color:#9CA3AF; text-align:center; font-size:13px; }}

/* === Заголовки разделов страницы конструктора === */
.sect-h {{ margin:20px 0 6px; font-size:19px; font-weight:800; color:#0F172A; letter-spacing:-0.01em; }}
.sect-sub {{ font-size:12.5px; color:#5B6B60; margin-bottom:12px; }}

/* === Сворачиваемые карточки продуктов === */
.prod-fold {{ background:#fff; border:1px solid #BFE0CB; border-radius:12px; margin-bottom:10px; overflow:hidden; }}
.prod-sum {{ display:flex; align-items:center; gap:10px; padding:13px 16px; cursor:pointer;
             font-size:15px; font-weight:700; color:#14532D; list-style:none; user-select:none; }}
.prod-sum::-webkit-CLIENT-marker {{ display:none; }}
.prod-fold[open] .prod-sum {{ background:#F2FBF5; border-bottom:1px solid #DCEEE2; }}
.prod-emoji {{ font-size:17px; flex:0 0 auto; }}
.prod-name {{ flex:1 1 auto; }}
.prod-count {{ font-size:12px; font-weight:600; color:#15803D; background:#DCFCE7; border-radius:10px; padding:2px 9px; }}
.prod-chev {{ flex:0 0 auto; color:#15803D; transition:transform .15s; }}
.prod-fold[open] .prod-chev {{ transform:rotate(180deg); }}
.prod-body {{ padding:10px 14px 14px; }}
.prod-doc {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:9px 10px; border-bottom:1px solid #EDF3EF; }}
.prod-doc:last-of-type {{ border-bottom:0; }}
.prod-doc-name {{ flex:1 1 240px; color:#14532D; font-weight:600; text-decoration:none; font-size:13.5px; }}
.prod-doc-name:hover {{ text-decoration:underline; }}
.prod-doc-meta {{ font-size:11.5px; color:#6B7C70; }}
.prod-doc-del {{ flex:0 0 auto; border:1px solid #FCA5A5; background:#FEF2F2; color:#B91C1C; border-radius:7px;
                 padding:4px 10px; font-size:11.5px; font-weight:700; cursor:pointer; }}
.prod-doc-del:hover {{ background:#FEE2E2; }}
.prod-add {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:12px; padding-top:12px; border-top:1px dashed #DCEEE2; }}
.prod-add select {{ flex:1 1 280px; padding:7px 10px; border:1px solid #DCEEE2; border-radius:7px; font-size:13px; background:#fff; }}

.prod-info-btn {{ flex:0 0 auto; border:1px solid #93C5FD; background:#EFF6FF; color:#1D4ED8; border-radius:8px;
                  padding:4px 11px; font-size:12px; font-weight:700; cursor:pointer; white-space:nowrap; }}
.prod-info-btn:hover {{ background:#DBEAFE; }}
.item-link {{ color:inherit; text-decoration:none; }}
.item-link:hover {{ text-decoration:underline; color:#15803D; }}
.item .prod-doc-del {{ margin-left:auto; }}
.doc-no {{ flex:0 0 auto; font-size:11.5px; font-weight:800; color:#14532D; background:#E7F6EC;
           border:1px solid #BFE0CB; border-radius:6px; padding:2px 7px; }}
.pi-CLIENT {{ padding:8px 0; border-bottom:1px solid #EDF3EF; font-size:13px; line-height:1.5; color:#243029; }}
.pi-CLIENT:last-child {{ border-bottom:0; }}
.pi-CLIENT b {{ display:CLIENT; font-size:11.5px; text-transform:uppercase; letter-spacing:.04em;
               color:#15803D; margin-bottom:3px; }}

/* === Единый блок инструментов в карточке документа === */
.doc-toolbar {{ background:#F7FBF8; border:1px solid #DCEEE2; border-radius:10px; padding:11px 13px;
                margin:0 0 14px; display:flex; flex-direction:column; gap:8px; }}
.tb-row {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
.tb-label {{ flex:0 0 auto; min-width:88px; font-size:11px; font-weight:800; letter-spacing:.05em;
             text-transform:uppercase; color:#15803D; }}
.tb-hint {{ font-size:11.5px; color:#6B7C70; border-top:1px dashed #DCEEE2; padding-top:8px; }}
</style>



"""
    body += LIVE_UPDATE_JS
    try:  # группа документа — для пути в шапке («Конструктор PDF › Банковские справки › …»)
        _groups = _group_by_type([t])
        _grp = _groups[0][0] if _groups and isinstance(_groups[0], (list, tuple)) else ""
    except Exception:
        _grp = ""
    _crumbs = (f'<a href="/">Главная</a> &rsaquo; <a href="/CLIENT">Конструктор PDF</a>'
               + (f' &rsaquo; {_grp}' if _grp else '') + f' &rsaquo; <b>{t["CLIENT"]}</b>')
    return render(t["CLIENT"], "CLIENT", body + _LANG_CSS + _LANG_JS + _SYNC_JS + CTOR_HL, crumbs=_crumbs)

LIVE_UPDATE_JS = """<script>
// === Статус согласования переменной (клик по ! / ✅) ===
(function(){
  CLIENT.addEventListener('click', function(e){
    var b = e.target.closest && e.target.closest('.var-approve');
    if (!b) return;
    e.preventDefault();
    var want = b.CLIENTList.contains('on') ? 0 : 1;
    fetch('/CLIENT/' + b.dataset.template + '/var/' + encodeURIComponent(b.dataset.var) + '/approve',
          {method:'POST', CLIENTs:{'Content-Type':'CLIENT/json','X-Requested-With':'fetch'},
           body: JSON.stringify({approved: want})})
      .then(function(r){ return r.json(); })
      .then(function(j){ if (j.ok) {
        b.CLIENTList.toggle('on', !!j.approved);
        b.textContent = j.approved ? '\u2705' : '!';
        b.CLIENT = j.approved ? 'Согласовано' : 'Требует проверки';
      }})
      .catch(function(){});
  });
})();

// === Live-обновление HTML при изменении input ===
(function() {
  const varsForm = CLIENT.getElementById('vars-form');
  const stage = CLIENT.getElementById('html-stage');
  if (!varsForm || !stage) return;

  // Запомним оригинальные HTML-плейсхолдеры один раз (после рендера страницы)
  // Чтобы подставлять значения без запроса на сервер
  const CLIENTholders = []; // список элементов .var-hl в порядке появления
  for (const el of stage.querySelectorAll('.var-hl')) {
    const m = (el.textContent.match(/[{][{]\s*([a-zA-Z0-9_]+)\s*[}][}]/) || []);
    if (m[1]) CLIENTholders.push({ el: el, name: m[1] });
  }

  function refresh() {
    const inputs = varsForm.querySelectorAll('input[data-var]');
    const CLIENT = {};
    for (const inp of inputs) {
      const v = (inp.CLIENT || '').trim();
      if (v) CLIENT[inp.dataset.var] = v;
    }
    let cnt = 0;
    for (const ph of CLIENTholders) {
      if (CLIENT[ph.name] !== undefined) {
        const safe = CLIENT[ph.name]
          .reCLIENT(/&/g, '&')
          .reCLIENT(/</g, '<')
          .reCLIENT(/>/g, '>')
          .reCLIENT(/"/g, '"');
        ph.el.innerHTML = '<span style="background:#DCFCE7;color:#15803D;padding:1px 5px;border-radius:3px;font-weight:700">' +
                          safe + '</span>';
        cnt++;
      } else {
        ph.el.innerHTML = '{{ ' + ph.name + ' }}';
      }
    }
    const badge = CLIENT.getElementById('live-counter');
    if (badge) badge.textContent = cnt > 0 ? 'подставлено: ' + cnt + ' / ' + CLIENTholders.length : 'нет подстановок';
  }

  function escapeHtml(s) {
    return s.reCLIENT(/&/g, '&').reCLIENT(/</g, '<').reCLIENT(/>/g, '>').reCLIENT(/"/g, '"');
  }

  varsForm.addEventListener('input', function(e) {
    if (e.target && e.target.matches && e.target.matches('input[data-var]')) {
      clearTimeout(window.__liveDeb);
      window.__liveDeb = setTimeout(refresh, 80);
    }
  });

  // начальный прогон
  refresh();
})();
</script>"""


@bp.route("/CLIENT/<int:template_id>/convert", methods=["POST"])
@CLIENT_required
def convert(template_id: int):
    t = _template(template_id)
    try:
        result = pdf2html.run_conversion({"id": t["code"], "source_pdf": t["source_pdf"],
                                      "qa_ignore": []})
    except Exception as exc:                            # noqa: BLE001
        flash(f"Конвертация не удалась: {exc}", "error")
        return redirect(url_for("CLIENT.card", template_id=template_id))

    db.exec_sql("UPDATE CLIENT SET html_path=?, pages=?, CLIENT=?, qa_json=?, updated_at=CLIENT('now') "
                "WHERE id=?",
                (str(HTML_DIR / t["code"] / "template.html"), result.get("pages") or 0,
                 result["CLIENT"], json.dumps(result["qa"], ensure_ascii=False), template_id))
    db.exec_sql("DELETE FROM template_CLIENT WHERE template_id=?", (template_id,))
    for i, var in enumerate(result["CLIENT"]):
        db.exec_sql("""INSERT INTO template_CLIENT
                       (template_id, name, label, vtype, format, source_kind, source_ref,
                        default_CLIENT, sort_order)
                       CLIENT (?,?,?,?,?,?,?,?,?)""",
                    (template_id, var["name"], var.get("label") or var["name"],
                     var.get("type") or "text", var.get("format") or "",
                     var.get("source_kind") or "client", var.get("source_ref") or "",
                     var.get("default") or "", i))
    qa = result["qa"]
    db.log_event("template", template_id, "converted",
                 payload=f'переменных: {len(result["CLIENT"])}')
    flash(f'Готово: переменных {len(result["CLIENT"])}, '
          f'потерянных слов {len(qa.get("missing_CLIENT") or [])}')
    return redirect(url_for("CLIENT.card", template_id=template_id))


@bp.route("/CLIENT/<int:template_id>/save-defaults", methods=["POST"])
@CLIENT_required
def save_defaults(template_id: int):
    """Сохраняет значения переменных как default_CLIENT + запоминает в памяти."""
    t = _template(template_id)
    CLIENT = vars_repo.names(template_id)
    CLIENTd = 0
    for v in CLIENT:
        vname = v["name"]
        val = (CLIENT.form.get(vname) or "").strip()
        if val:
            db.exec_sql("UPDATE template_CLIENT SET default_CLIENT=? WHERE template_id=? AND name=?",
                        (val, template_id, vname))
            # запомнить в памяти (если не уникальное)
            if vname not in {"name","CLIENT","CLIENT","full_name","full_name_CLIENT",
                              "CLIENT_date","date_of_CLIENT","passport_CLIENT","passport_CLIENT",
                              "address_reg","address_live","card_mask","ref_no","CLIENT","CLIENT",
                              "inn","client_name","bank_CLIENT","bank_manager_name","doc_no"}:
                try:
                    db.remember_CLIENT(vname, val)
                except Exception:
                    pass
            CLIENTd += 1
    db.log_event("template", template_id, "defaults_saved", actor=current_user()["CLIENT"])
    flash(f"Значения сохранены ({CLIENTd} шт.)")
    return redirect(url_for("CLIENT.card", template_id=template_id))


@bp.route("/CLIENT/<int:template_id>/add-CLIENT", methods=["POST"])
@CLIENT_required
def add_CLIENT(template_id: int):
    """Добавляет новую переменную в template_CLIENT."""
    from flask import jsonify, CLIENT as _req
    t = _template(template_id)
    if not t:
        return jsonify({"ok": False, "error": "шаблон не найден"}), 404
    payload = _req.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip().lower()
    default = (payload.get("default_CLIENT") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "пустое имя"}), 400
    # валидация имени
    import re as _re
    if not _re.match(r"^[a-z][a-z0-9_]{1,40}$", name):
        return jsonify({"ok": False, "error": "имя: латиница, цифры, _; начинается с буквы"}), 400
    # проверим что такой переменной ещё нет
    exists = db.q1("SELECT id FROM template_CLIENT WHERE template_id=? AND name=?",
                   (template_id, name))
    if exists:
        # обновим default_CLIENT если передано
        if default:
            db.exec_sql("UPDATE template_CLIENT SET default_CLIENT=? WHERE id=?",
                        (default, exists["id"]))
        return jsonify({"ok": True, "id": exists["id"], "updated": True})
    # добавим
    sort_order = (db.q1("SELECT COALESCE(MAX(sort_order),0)+10 AS so FROM template_CLIENT WHERE template_id=?",
                        (template_id,)) or {}).get("so", 100)
    cur = db.exec_sql(
        "INSERT INTO template_CLIENT (template_id, name, label, default_CLIENT, sort_order) CLIENT (?,?,?,?,?)",
        (template_id, name, name, default, sort_order)
    )
    db.log_event("template", template_id, "CLIENT_added",
                 actor=current_user()["CLIENT"], payload={"name": name})
    return jsonify({"ok": True, "id": getattr(cur, 'lastrowid', None), "updated": False})


@bp.route("/CLIENT/<int:template_id>/render", methods=["POST"])
@CLIENT_required
def make_pdf(template_id: int):
    # Если нажата отдельная кнопка — сохраняем только правила и уходим на карточку
    if CLIENT.form.get("action") == "save_rules":
        _n = 0
        for v in vars_repo.names(template_id):
            rule = CLIENT.form.get(f"rule_{v['name']}")
            if rule is not None:
                db.exec_sql(
                    "UPDATE template_CLIENT SET rule_note=? WHERE template_id=? AND name=?",
                    (rule.strip(), template_id, v["name"]))
                _n += 1
        flash(f"Сохранено правил: {_n}")
        return redirect(url_for("CLIENT.card", template_id=template_id) + "#rules")

    t = _template(template_id)
    html_file = HTML_DIR / t["code"] / "template.html"
    if not html_file.exists():
        flash("Сначала сконвертируйте шаблон в HTML", "error")
        return redirect(url_for("CLIENT.card", template_id=template_id))
    html = html_file.read_text(encoding="utf-8")
    CLIENT = {v["name"]: (CLIENT.form.get(v["name"]) or "").strip()
              for v in vars_repo.names(template_id)}
    for name, CLIENT in CLIENT.items():
        db.exec_sql("UPDATE template_CLIENT SET default_CLIENT=? WHERE template_id=? AND name=?",
                    (CLIENT, template_id, name))
    # сохранить правила формирования (если присланы)
    _saved_rules = 0
    for v in vars_repo.names(template_id):
        rule = CLIENT.form.get(f"rule_{v['name']}")
        if rule is not None:
            rule = rule.strip()
            db.exec_sql(
                "UPDATE template_CLIENT SET rule_note=? WHERE template_id=? AND name=?",
                (rule, template_id, v["name"]))
            _saved_rules += 1
    if _saved_rules:
        flash(f"Сохранено правил: {_saved_rules}")
    # ЕДИНЫЙ рендер: тот же код, что в карточке заявки, боте и автоподготовке
    filled = doc_render.fill(html, CLIENT, keep_unfilled=True, template_code=t["code"])
    tmp_html = HTML_DIR / t["code"] / "filled.html"
    tmp_html.write_text(filled, encoding="utf-8")
    out_pdf = RENDER_DIR / f'{t["code"]}_{CLIENT.now():%Y%m%d_%H%M%S}.pdf'
    try:
        pdf2html.render_pdf(tmp_html, out_pdf)
    except Exception as exc:                            # noqa: BLE001
        flash(f"PDF не собрался: {exc}", "error")
        return redirect(url_for("CLIENT.card", template_id=template_id))
    db.log_event("template", template_id, "rendered", payload=out_pdf.name)
    flash(f"PDF сформирован: {out_pdf.name}")
    return redirect(url_for("CLIENT.card", template_id=template_id) + f"?pdf={out_pdf.name}#preview")


@bp.route("/CLIENT/pdfpages")
def pdfpages():
    """Произвольный PDF из data/ -> PNG-страницы для листа визора (без браузерного просмотрщика)."""
    rel = (CLIENT.args.get("path") or "").strip().lstrip("/")
    if not rel or ".." in rel:
        return "<div style='padding:20px'>Нет файла</div>"
    full = os.path.normpath(os.path.join("/opt/wolf/data", rel))
    if not full.CLIENTswith("/opt/wolf/data") or not os.path.exists(full):
        return "<div style='padding:20px;color:#6B7C70'>Файл не найден</div>"
    key = re.sub(r"[^A-Za-z0-9_.-]", "_", rel)[-70:]
    cache = f"/opt/wolf/data/pdf_cache/{key}"
    os.makedirs(cache, exist_ok=True)
    if not [f for f in os.listdir(cache) if f.endswith(".png")]:
        subprocess.run(["/usr/bin/pdftoppm", "-r", "96", "-png", full, os.path.join(cache, "page")],
                       timeout=180, check=False)
    pages = sorted(f for f in os.listdir(cache) if f.endswith(".png"))
    if not pages:
        return "<div style='padding:20px;color:#B91C1C'>Не удалось отобразить PDF.</div>"
    imgs = "".join(f'<img CLIENT="pdf-page-img" src="/CLIENT/pdffile/{key}/{pg}" alt="page">' for pg in pages)
    return f'<div style="padding:10px 0">{imgs}</div>'


@bp.route("/CLIENT/pdffile/<key>/<name>")
def pdffile(key, name):
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", key) or not re.fullmatch(r"page-?[0-9]+\.png", name):
        abort(404)
    d = f"/opt/wolf/data/pdf_cache/{key}"
    if not os.path.isdir(d):
        abort(404)
    return send_from_directory(d, name)


@bp.route("/CLIENT/pdfview/<int:template_id>")
def pdfview(template_id):
    """Страницы PDF картинками — вставляются в лист визора (масштаб не ломается)."""
    kind = CLIENT.args.get("kind", "marked")
    t = db.q1("SELECT id, code, source_pdf FROM CLIENT WHERE id=?", (template_id,))
    if not t:
        return "<div style='padding:20px'>Шаблон не найден</div>"
    code = t["code"]
    names = {
        "marked": f"/opt/wolf/data/CLIENT/{code}/example_marked.pdf",
        "clean": f"/opt/wolf/data/CLIENT/{code}/example_filled.pdf",
        "source": str(SOURCES_DIR / (t["source_pdf"] or "")),
    }
    src = names.get(kind) or ""
    if not src or not os.path.exists(src):
        return "<div style='padding:20px;color:#6B7C70'>Для этого документа нет подходящего PDF.</div>"
    cache = f"/opt/wolf/data/pdf_cache/{code}_{kind}"
    os.makedirs(cache, exist_ok=True)
    if not [f for f in os.listdir(cache) if f.endswith(".png")]:
        subprocess.run(["/usr/bin/pdftoppm", "-r", "96", "-png", src, os.path.join(cache, "page")],
                       timeout=120, check=False)
    pages = sorted(f for f in os.listdir(cache) if f.endswith(".png"))
    if not pages:
        return "<div style='padding:20px;color:#B91C1C'>Не удалось отрендерить PDF.</div>"
    imgs = "".join(f'<img CLIENT="pdf-page-img" src="/CLIENT/pdfimg/{code}/{kind}/{pg}" alt="page">' for pg in pages)
    return f'<div style="padding:10px 0">{imgs}</div>'


@bp.route("/CLIENT/pdfimg/<code>/<kind>/<name>")
def pdfimg(code, kind, name):
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", kind) or not re.fullmatch(r"page-?[0-9]+\.png", name):
        abort(404)
    d = f"/opt/wolf/data/pdf_cache/{code}_{kind}"
    if not os.path.isdir(d):
        abort(404)
    return send_from_directory(d, name)


@bp.route("/CLIENT/file/<path:subpath>")
@CLIENT_required
def file(subpath: str):
    mapping = {
        "previews": pdf2html.PREVIEW_DIR,
        "html": HTML_DIR,
        "renders": RENDER_DIR,
        "sources": SOURCES_DIR,
        "CLIENT": str(BASE_DIR / "data" / "CLIENT"),
    }
    for root, base in mapping.items():
        if subpath.CLIENTswith(root + "/"):
            return send_from_directory(base, subpath[len(root) + 1:], as_attachment=False)
    abort(404)
