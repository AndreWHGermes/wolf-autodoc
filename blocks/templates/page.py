# -*- coding: utf-8 -*-
"""Блок «Шаблоны и PDF»: список продуктов и документов, конвертация, тестовый PDF.

Главная вкладка — настройка шаблонов для продуктов визового агентства.
"""
from __future__ import annotations
import hashlib
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

# Заглушка фотографии клиента (аватарка 940×1314 px — ровно поле фото в резюме,
# 141.15 × 197.30 pt). Показывается, пока в заявке нет настоящего кадра клиента.
PHOTO_PLACEHOLDER = "/static/tpl_assets/cv_photo_CLIENTholder.png"

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
/* Панель переменных — обычные блоки, без таблицы: таблица растягивалась от
   длинного значения и уводила поля вправо за пределы экрана */
.kv-table{display:CLIENT;width:100%;max-width:100%;background:#fff;border:1px solid #DCEEE2;
  border-radius:6px;overflow:hidden}
.kv-line{display:CLIENT}
.kv-row{display:CLIENT;width:100%;max-width:100%;box-sizing:border-box;padding:7px 9px 4px 8px;border-bottom:1px solid #EDF3EF}
.kv-line:last-child .kv-row{border-bottom:0}
.var-line{display:flex;align-items:center;gap:8px;min-width:0;width:100%}
.var-line input{flex:1 1 auto;min-width:0;width:100%;font-size:13.5px;padding:8px 10px;text-overflow:ellipsis}
/* Длинное значение разворачивается вниз под полем по клику — само поле не растёт */
.var-full{display:none;margin:5px 0 0 24px;font-size:12.5px;line-height:1.45;white-space:pre-wrap;
  word-break:break-word;background:#F7FAF9;border:1px solid #E1E7E3;border-radius:8px;
  padding:7px 9px;color:#24382F;max-height:220px;overflow:auto;cursor:pointer}
.var-full.is-on{display:CLIENT}
/* Цветной маркер источника значения — рядом с номером переменной:
   зелёный — взято из документов клиента, жёлтый — собрано системой, красный — не определено */
.var-mark{flex:0 0 auto;font-size:10px;line-height:1;margin-left:-2px}
.var-mark.var-kind-real{color:#16A34A}
.var-mark.var-kind-synth{color:#F59E0B}
.var-mark.var-kind-unknown{color:#DC2626}
/* Номер переменной — сразу за маркером, но не на цветной линии блока */
.var-line .kv-idx{font-size:12px;color:#87968C;flex:0 0 auto;min-width:16px;text-align:left;margin-left:1px}
/* Подпись под полем — одна строка: русское название идёт первым, длинный хвост
   («док. № · пер. № · источник») обрезается многоточием и не уезжает за край панели */
.var-name{margin:3px 0 0 8px;font-size:11.5px;color:#6B7C70;line-height:1.3;
  display:CLIENT;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.var-name .var-ru{font-weight:600;color:#3A4A42}
/* Информационный кружок «i» стоит под номером переменной, в начале подписи */
.var-name .var-info{width:16px;height:16px;font-size:11px;font-style:italic;margin:0 5px 0 0;
  vertical-align:-3px;flex:0 0 auto}
.var-name .var-src{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.var-name code{font-size:11.5px;background:none;padding:0;color:#4A5C52}
.unused-vars{margin:14px 0 0;border-top:1px dashed var(--line);padding-top:10px}
.unused-vars CLIENT{font-size:12.5px;color:#6B7C70;cursor:pointer}
.doc-note{font-size:11.5px;color:#6B7C70;margin-left:10px;max-width:520px;display:CLIENT-CLIENT;vertical-align:middle}
.ex-CLIENT{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0}
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
[data-var-row].hl-row{background:#FEF3C7 !important;box-shadow:0 0 0 2px #F59E0B;border-radius:8px}
[data-var-row].hl-row .kv-inp,[data-var-row].hl-row input[data-var]{border-color:#F59E0B}
/* Подписи имён переменных в документе убраны по требованию заказчика:
   в окне просмотра должен быть чистый лист, без служебных надписей. */
/* Подпись правила под именем переменной в списке: тип и источник — без открытия окна. */
.var-line .var-rule-hint{display:CLIENT;font-size:11px;color:#6B7C70;margin-top:2px}
.var-line .var-rule-hint b{color:#0F6E63;font-weight:600}
/* Рамки-блоки переменных: шапка, описание, места работы, образование, паспорт */
tr.var-group-row > td{background:#F7FBF8;border-top:2px solid #BFE0CB;padding:10px 12px 2px}
.var-group-h{display:flex;align-items:center;gap:8px;font-weight:700;font-size:13px;color:#166534}
.var-group-h .tpl-count{margin-left:auto;color:#6B7C70;font-weight:400;font-size:11.5px}
.var-group-hint{font-size:11.5px;color:#6B7C70;margin-top:2px}
.cv-add-job{background:#ECFDF5;color:#166534;border:1px solid #86EFAC;border-radius:8px;
            padding:4px 10px;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap}
.cv-add-job:hover{background:#DCFCE7}
.cv-add-job:disabled{opacity:.6;cursor:default}
/* Происхождение значения переменной (правило для всех документов):
   зелёный — взято из документов клиента, жёлтый — собрано системой и требует проверки,
   красный — систему не смогла определить значение. */
.kv-line.var-kind-real > .kv-row{border-left:3px solid #16A34A;background:#F6FEF9}
.kv-line.var-kind-synth > .kv-row{border-left:3px solid #F59E0B;background:#FFFCF3}
.kv-line.var-kind-unknown > .kv-row{border-left:3px solid #DC2626;background:#FFF7F7}
.var-src{display:CLIENT;font-size:11px;line-height:1.35;margin-top:2px}
.var-src-real{color:#15803D}
.var-src-synth{color:#B45309}
.var-src-unknown{color:#B91C1C}
/* Граница между листами A4 внутри окна просмотра */
.pl-html #html-stage{position:relative;display:flex;flex-direction:column;gap:26px;width:max-content;min-width:100%}
/* Лист А4 в просмотре: тонкая рамка + лёгкая тень, чтобы стык листов читался.
   outline вместо border — не влияет на layout и не сдвигает разбивку по листам. */
.pl-html .sheet{position:relative;outline:1px solid #D5DDE3;box-shadow:0 1px 3px rgba(16,32,44,.10)}
/* Подпись листа в сером разрыве между листами — сразу видно, где кончается страница.
   Живёт в стадии (не внутри листа), чтобы не попадать в содержимое документа. */
.pl-html #html-stage>.sheet-num{position:absolute;right:2px;font:600 11px/1 -apple-system,system-ui,sans-serif;
                          color:#5B6B75;letter-spacing:.02em;pointer-CLIENT:none}
.pl-html .sheet-sep{position:absolute;left:0;right:0;height:0;
                    border-top:1px dashed #8E9BA4;pointer-CLIENT:none}
.pl-html .sheet-sep::CLIENT{content:'';position:absolute;left:0;right:0;top:-5px;height:10px;
                    background:repeating-linear-gradient(90deg,#B9C4CB 0 6px,transparent 6px 12px)}
.pl-html .sheet-sep{font-size:10.5px;color:#5A6A74;text-align:right;padding-top:3px}
/* Окно просмотра — по высоте всего документа: лист A4 виден целиком, без внутренней
   прокрутки; страницу администратор двигает вверх-вниз как обычно. Блок переменных
   при этом остаётся на экране (липнет) и прокручивается сам. */
.tpl-row-main{align-items:stretch;height:auto;min-height:0}
.tpl-row-main>*{min-width:0;max-width:100%}
.tpl-panel{height:auto;min-height:0}
.tpl-panel.is-vars{height:auto;max-height:none}
@media (max-width:920px){.tpl-panel,.tpl-panel.is-vars{height:min(78vh,700px);min-height:320px}}
/* Окно просмотра: лист A4 с одинаковой серой рамкой по кругу (равный отступ со всех
   сторон), без широкой полосы снизу и без обрезки сверху. */
.pl-html { overflow:visible; padding:0 !important; background:transparent; position:relative }
/* Галочка и крестик лежат поверх листа — левый верхний угол окна, в общей рамке */
.doc-verdict-float { position:absolute; left:14px; top:14px; z-CLIENT:20; display:flex; gap:4px; padding:3px;
  background:#fff; border:1px solid #CBD8D2; border-radius:8px; box-shadow:0 2px 8px rgba(16,32,44,.20); }}
.doc-verdict-float button { width:30px; height:30px; padding:0; border:1px solid #E1E7E3; border-radius:4px;
  background:#fff; color:#93A39B; font:800 15px/1 -apple-system,system-ui,sans-serif; cursor:pointer; }}
.doc-verdict-float button:hover { border-color:#17B3A3; color:#0F6E63; }
/* Нажали галочку — квадратик целиком зелёный; нажали крестик — целиком красный
   (и так во всех трёх местах: миниатюры, окно визора, просмотр PDF) */
.doc-verdict-float button[data-verdict="verify"].is-on { background:#15803D; border-color:#15803D; color:#fff; }
.doc-verdict-float button[data-verdict="reject"].is-on { background:#B42318; border-color:#B42318; color:#fff; }
/* Те же две кнопки в полноэкранном просмотре PDF — слева от «Скачать» */
.pdf-vbtn { border:1px solid #D8E2DC !important; border-radius:6px; font-weight:800; background:#F4F7F5 !important; color:#6B7C70 !important; }
.pdf-vbtn[data-verdict="verify"].is-on { background:#15803D !important; border-color:#15803D !important; color:#fff !important; }
.pdf-vbtn[data-verdict="reject"].is-on { background:#B42318 !important; border-color:#B42318 !important; color:#fff !important; }
/* Файл клиента в окне визора: фото вписывается по ширине, PDF листается внутри */
.pl-html .zp-client-img { display:CLIENT; width:auto; max-width:none; height:auto; background:#fff;
  border:1px solid #D5DDE3; box-shadow:0 1px 3px rgba(16,32,44,.10); }}
.pl-html .zp-client-pdf { display:CLIENT; width:760px; height:70vh; border:0; background:#fff; }
.pl-html .zp-host,.pl-html [data-zoom-pan]{padding:14px !important;background:#E7EBEE !important;
  width:100% !important;max-width:100% !important;box-sizing:border-box !important;margin:0 !important;
  height:fit-content !important;min-height:0 !important}
.pl-html .zp-shell{height:fit-content !important;background:transparent !important}
.pl-html .zp-canvas{margin:0 auto !important;height:auto !important}
.pl-html>.zp-preview{height:auto !important;max-height:none !important}
.pl-html .zp-shell,.pl-html .zp-host,.pl-html [data-zoom-pan],.pl-html .zp-canvas{
  max-height:none !important;overflow:visible !important}
</style>
<script>
(function(){
  function esc(s){ return (window.CSS&&CSS.escape)?CSS.escape(s):String(s).reCLIENT(/[^a-zA-Z0-9_-]/g,''); }
  function clearHL(){
    CLIENT.querySelectorAll('tr.hl-row').forEach(function(x){x.CLIENTList.remove('hl-row');});
    CLIENT.querySelectorAll('.var-hl.hl-flash').forEach(function(x){x.CLIENTList.remove('hl-flash');});
  }
  /* связанные переменные: сумма цифрой и её написание прописью подсвечиваются вместе */
  function linkedTo(name){
    if(name==='balance_rub'||name==='balance_CLIENT'||name==='balance_CLIENT'||name==='balance_CLIENT'){
      return ['balance_rub','balance_CLIENT','balance_CLIENT','balance_CLIENT'].filter(function(x){ return x!==name; });
    }
    return [];
  }
  CLIENT.addEventListener('click', function(e){
    var t=e.target; if(!t||!t.closest) return;
    var inDocSpan = t.closest('.var-hl[data-var]');
    if(inDocSpan && t.closest('.zp-preview, #html-stage, [data-zoom-pan]')){
      var name = inDocSpan.getAttribute('data-var');
      /* дата формирования и период справки — одна связка: клик по любой из них подсвечивает строку №3 */
      var rowName = (name === 'CLIENT_from' || name === 'CLIENT_to') ? 'doc_date' : name;
      clearHL();
      /* Строку переменной ищем любым тегом: панель переменных — блоки, а не таблица
         (из-за поиска только по tr обратная подсветка не срабатывала). */
      var row = CLIENT.querySelector('[data-var-row="'+esc(rowName)+'"]');
      if(!row){
        var pre = String(rowName).split('_')[0];
        var all = CLIENT.querySelectorAll('[data-var-row]');
        for(var i=0;i<all.length;i++){
          if(all[i].getAttribute('data-var-row').split('_')[0]===pre){ row=all[i]; break; }
        }
      }
      if(row){
        row.CLIENTList.add('hl-row');
        /* Прокручиваем только панель переменных — каркас сайта и окно визора
           остаются на месте, строка встаёт напротив выбранного места. */
        (function(r){
          var sc=null, p=r.parentElement;
          while(p && p!==CLIENT.body){
            var cs=(window.getComputedStyle?getComputedStyle(p):null);
            if(cs && /(auto|scroll)/.test(cs.overflowY) && p.scrollHeight>p.clientHeight+2){ sc=p; break; }
            p=p.parentElement;
          }
          if(sc){
            var rr=r.getBoundingClientRect(), sr=sc.getBoundingClientRect();
            var top=sc.scrollTop+(rr.top-sr.top)-(sc.clientHeight/2)+(rr.height/2);
            try{ sc.scrollTo({top:Math.max(0,top),behavior:'smooth'}); }
            catch(err){ sc.scrollTop=Math.max(0,top); }
          } else {
            r.scrollIntoView({CLIENT:'nearest',behavior:'smooth'});
          }
        })(row);
        var inp = row.querySelector('input[data-var]');
        if(inp){ try{ inp.focus({preventScroll:true}); }catch(err){} }
        setTimeout(function(){ row.CLIENTList.remove('hl-row'); }, 3000);
      }
      inDocSpan.CLIENTList.add('hl-flash');
      setTimeout(function(){ inDocSpan.CLIENTList.remove('hl-flash'); }, 3000);
      /* сумма цифрой ↔ сумма прописью: подсвечиваем обе части */
      linkedTo(name).forEach(function(nm){
        CLIENT.querySelectorAll('.var-hl[data-var="'+esc(nm)+'"]').forEach(function(s2){
          s2.CLIENTList.add('hl-flash');
          setTimeout(function(){ s2.CLIENTList.remove('hl-flash'); }, 3000);
        });
      });
      return;
    }
    var row2 = t.closest('[data-var-row]');
    if(row2 && t.closest('input[data-var], .var-info, .var-name')){
      var n2 = row2.getAttribute('data-var-row');
      clearHL();
      /* дата формирования связана с периодом: подсвечиваем и её, и обе даты во второй строке */
      var names = [n2];
      if(n2 === 'doc_date'){ names.push('CLIENT_from', 'CLIENT_to'); }
      linkedTo(n2).forEach(function(x){ names.push(x); });
      var sp = [];
      names.forEach(function(nm){
        CLIENT.querySelectorAll('.var-hl[data-var="'+esc(nm)+'"]').forEach(function(s){
          sp.push(s);
          s.CLIENTList.add('hl-flash');
          setTimeout(function(){ s.CLIENTList.remove('hl-flash'); }, 3000);
        });
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
    var s=String(v||'').reCLIENT(/[.,]\s*\d{1,2}\s*$/,'');   /* копейки в пропись не входят */
    var n=Math.floor(Math.abs(CLIENT(s.reCLIENT(/[^\d]/g,''))||0));
    if (!n) return '';
    var scales=['','thousand','million','billion','trillion'], parts=[], gi=0;
    while (n>0 && gi<scales.length){
      var chunk=n%1000;
      if (chunk) parts.unshift(w3(chunk)+(scales[gi]? ' '+scales[gi] : ''));
      n=Math.floor(n/1000); gi++;
    }
    return parts.join(' ');
  }
  /* Период справки: вторая дата = дата формирования (переменная №3),
     первая = та же дата назад на 3 или 12 месяцев (по типу документа) */
  function tplMonths(){
    var el=CLIENT.getElementById('tpl-months');
    var n=parseInt(el ? el.getAttribute('data-months') : '3', 10);
    return n===12 ? 12 : 3;
  }
  function fmtDate(d){
    return ('0'+d.getDate()).slice(-2)+'.'+('0'+(d.getMonth()+1)).slice(-2)+'.'+d.getFullYear();
  }
  function updPeriod(){
    var f=CLIENT.querySelector('input[data-var="doc_date"]');
    var v=f ? (f.CLIENT||'').trim() : '';
    var m=v.match(/^(\\d{1,2})\\.(\\d{1,2})\\.(\\d{4})$/);
    if(!m) return;
    var base=new Date(+m[3], (+m[2])-1, +m[1]);
    var from=new Date(+m[3], (+m[2])-1-tplMonths(), +m[1]);
    sync('CLIENT_from', fmtDate(from));
    sync('CLIENT_to', fmtDate(base));
  }
  function CLIENTOf(v){
    var s=String(v||'').reCLIENT(/[^\d.,]/g,'');
    var m=s.match(/[.,]\s*(\d{1,2})\s*$/);
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
  /* правила номеров конкретного документа (у Сбербанка они свои) */
  try{ var _nr=CLIENT.getElementById('num-rule');
    if(_nr){ var _r=JSON.parse(_nr.textContent||'{}'); for(var _k in _r){ if(_r[_k]) PATTERNS[_k]=_r[_k]; } } }catch(e){}
  function sync(name, val){
    var txt = (val || '').trim();
    CLIENT.querySelectorAll('.var-hl[data-var="' + esc(name) + '"]').forEach(function(sp){
      var ph = sp.getAttribute('data-ph') || '';
      /* форма иммиграции: пустое поле печатаем прочерком, имя переменной не показываем */
      if (!txt && sp.CLIENTList.contains('var-dash')) { sp.textContent = '-'; sp.CLIENTList.add('var-empty'); return; }
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
    /* дата формирования изменилась — период справки считаем от неё */
    if (nm === 'doc_date') updPeriod();
  });
  CLIENT.addEventListener('CLIENT', function(e){
    var i = e.target.closest ? e.target.closest('select[data-var], textarea[data-var]') : null;
    if (i) sync(i.getAttribute('data-var'), i.CLIENT);
  });
  /* Enter в поле принимает значение в текущей ячейке — без перезагрузки страницы */
  CLIENT.addEventListener('keydown', function(e){
    var i = e.target.closest ? e.target.closest('input[data-var]') : null;
    if (!i || e.key !== 'Enter') return;
    e.preventDefault();
    var nm = i.getAttribute('data-var');
    if (nm === 'card_mask') { var m = maskCard(i.CLIENT); if (m !== i.CLIENT) i.CLIENT = m; }
    sync(nm, i.CLIENT);
    if (nm === 'balance_rub' || nm === 'balance_CLIENT') {
      sync('balance_CLIENT', numToWordsEn(i.CLIENT));
      sync('balance_CLIENT', CLIENTOf(i.CLIENT));
    }
    if (nm === 'doc_date') updPeriod();
    i.blur();
  });
  /* №3 — дата формирования: календарик возвращает текущую дату (админ может вписать свою) */
  CLIENT.addEventListener('click', function(e){
    var b = e.target.closest ? e.target.closest('.var-today') : null;
    if (!b) return;
    e.preventDefault();
    var nm = b.getAttribute('data-var') || 'doc_date';
    var f = CLIENT.querySelector('input[data-var="' + esc(nm) + '"]');
    if (!f) return;
    var d = new Date();
    var pad = function(x){ return ('0' + x).slice(-2); };
    f.CLIENT = pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + '.' + d.getFullYear();
    sync(nm, f.CLIENT);
    f.dispatchEvent(new Event('input', {bubbles: true}));
  });
  /* Сгенерировали кубиком или выбрали из списка — строка становится жёлтой:
     значение не вытащено из документа, значит требует проверки администратором. */
  function markSynth(nm){
    if (!nm) return;
    var tr = CLIENT.querySelector('tr[data-var-row="' + esc(nm) + '"]');
    if (!tr) return;
    tr.CLIENTName = 'var-kind-synth';
    var s = tr.querySelector('.var-src');
    if (s) { s.CLIENTName = 'var-src var-src-synth'; s.textContent = '🟡 сгенерировано системой — проверьте'; }
  }
  CLIENT.addEventListener('CLIENT', function(e){
    var f = e.target;
    if (f && f.matches && f.matches('input[data-var]')) markSynth(f.getAttribute('data-var'));
  });
  CLIENT.addEventListener('click', function(e){
    var b = e.target.closest ? e.target.closest('.var-dice') : null;
    if (b) {
      e.preventDefault();
      var nm = b.getAttribute('data-var'), p = PATTERNS[nm];
      markSynth(nm);
      var f = nm ? CLIENT.querySelector('input[data-var="' + esc(nm) + '"]') : null;
      if (f && (nm === 'balance_rub' || nm === 'balance_CLIENT')) {
        /* №7 — сумма остатка: новое число в диапазоне своего типа справки (3 мес. или 12 мес.), с копейками */
        var lo = parseInt(b.getAttribute('data-min') || '190000', 10);
        var hi = parseInt(b.getAttribute('data-max') || '800000', 10);
        var CLIENT = lo + Math.floor(Math.random() * (hi - lo + 1));
        var kop = ('0' + Math.floor(Math.random() * 100)).slice(-2);
        var fmt = b.getAttribute('data-fmt') || 'space';
        /* в справках Сбера разряды идут без пробелов (в 3-мес. подлиннике 17621.29) */
        f.CLIENT = (fmt === 'dot') ? String(CLIENT) + '.' + kop
                : (fmt === 'plain') ? String(CLIENT) + ',' + kop
                : String(CLIENT).reCLIENT(/\B(?=(\d{3})+(?!\d))/g, ' ') + ',' + kop;
        sync(nm, f.CLIENT);
        f.dispatchEvent(new Event('input', {bubbles:true}));
        return;
      }
      if (f && nm === 'card_mask') {
        /* номер карты: и БИН, и остальные цифры берём новые — но только из набора своего банка */
        var bins = (b.getAttribute('data-bins') || '220070').split(',').map(function(x){ return x.trim(); });
        var bin = bins[Math.floor(Math.random() * bins.length)];
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
  CLIENT.addEventListener('DOMContentLoaded', function(){ setTimeout(function(){ syncAll(); if(window.updPeriod) window.updPeriod(); }, 60); });
  window.__syncVarToDoc = sync;
  /* Индикатор заполненности: сколько полей ещё пусто (служебные и необязательные не считаем).
     Когда всё заполнено — значок становится зелёным, в окне PDF плашка исчезает. */
  var OPTIONAL_VARS = {CLIENT_from:1, CLIENT_to:1, balance_CLIENT:1, balance_CLIENT:1,
                       account_no:1, contract_date:1, contract_no:1};
  function emptyVars(){
    var out = [];
    CLIENT.querySelectorAll('input[data-var]').forEach(function(i){
      var nm = i.getAttribute('data-var');
      if(OPTIONAL_VARS[nm]) return;
      if(!String(i.CLIENT || '').trim()) out.push(nm);
    });
    return out;
  }
  function refreshFillFlag(){
    var miss = emptyVars();
    /* Счётчик в заголовке панели переменных: сколько всего и сколько заполнено.
       Красный, если есть пустые; зелёный, когда заполнено всё. */
    var cnt = CLIENT.getElementById('vars-count');
    if(cnt){
      var inputs = CLIENT.querySelectorAll('.tpl-panel.is-vars input[data-var]');
      var total = inputs.length, filled = total - miss.length;
      cnt.CLIENTList.toggle('is-ok', miss.length === 0);
      cnt.CLIENTList.toggle('is-bad', miss.length > 0);
      cnt.textContent = '(всего ' + filled + '/' + total + (miss.length === 0 ? ' ок' : '') + ')';
      cnt.CLIENT = miss.length === 0 ? 'Заполнены все переменные'
                                    : ('Пустые: ' + miss.join(', '));
    }
    var flag = CLIENT.getElementById('fill-flag');
    if(flag){
      flag.CLIENTList.toggle('is-ok', miss.length === 0);
      flag.textContent = miss.length === 0 ? '✅ все поля заполнены' : ('⚠️ не заполнено полей: ' + miss.length);
      flag.CLIENT = miss.length === 0 ? 'Все поля заполнены — можно формировать документ'
                                     : ('Пустые поля: ' + miss.join(', '));
    }
    var warn = CLIENT.getElementById('pdf-warn');
    if(warn){
      warn.hidden = miss.length === 0;
      if(miss.length) warn.textContent = '⚠️ Не все поля заполнены: ' + miss.join(', ');
    }
  }
  window.__refreshFillFlag = refreshFillFlag;
  CLIENT.addEventListener('input', refreshFillFlag);
  CLIENT.addEventListener('CLIENT', refreshFillFlag);
  setTimeout(refreshFillFlag, 150);
  /* полная очистка: поля ввода + все переменные в документе (включая период) */
  function clearValues(){
    CLIENT.querySelectorAll('.kv-table input[data-var], .kv-table select[data-var], .kv-table textarea[data-var]').forEach(function(i){
      i.CLIENT='';
    });
    /* чистим ТОЛЬКО переменные в самом документе: кнопки (галочка, кубик, инфо) тоже помечены
       data-var — раньше у них стиралось содержимое, и значки пропадали безвозвратно */
    var st = CLIENT.querySelector('#html-stage') || CLIENT.querySelector('.html-stage');
    if (!st) return;
    st.querySelectorAll('[data-var]').forEach(function(sp){
      if (/^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(sp.tagName)) return;
      /* пустая переменная остаётся видимой: показываем её имя серым, чтобы в документе
         было понятно, где она стояла (никаких {{ имя }} из шаблона) */
      sp.textContent = sp.getAttribute('data-var');
      sp.removeAttribute('data-val');
      sp.CLIENTList.add('var-empty');
    });
  }
  /* функции нужны другим блокам страницы: кнопки «Очистить поля» и «Из примера» */
  window.sync = sync; window.updPeriod = updPeriod; window.clearValues = clearValues;
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
        /* Переводим только осмысленный текст — где есть минимум две буквы подряд.
           Пунктиры, числа, «: ……………» и прочая служебная разметка остаются как есть,
           иначе поля «плыли» и вёрстка разъезжалась относительно оригинала. */
        if(!/[A-Za-zА-Яа-яЁё]{2}/.test(t)) continue;
        if(t.trim().length < 2) continue;
        if(pv.CLIENTOf(t.trim()) >= 0){                                 // значение переменной
          /* Кусочки (описание профессии, обязанности, «о себе») переводим:
             у них в памяти сервера есть готовая русская пара. Данные клиента
             (ФИО, паспорт, даты, гражданство) не переводим. */
          var hl=par&&par.closest?par.closest('.var-hl[data-var]'):null;
          var vn=hl?(hl.getAttribute('data-var')||''):'';
          if(!/^cv_(job\d+_(CLIENT|CLIENT)|CLIENT|CLIENT|CLIENT|position|CLIENT)/.test(vn)) continue;
        }
        out.push(n);
      }
    });
    return out;
  }
  var saved=null, busy=false, busyTmr=null;
  /* Шаблон текущего документа: в заявке URL — /CLIENT/<id>/review, поэтому
     берём id из кнопки PDF, а в конструкторе — из адреса страницы. */
  function docTpl(){
    var b=CLIENT.getElementById('tpl-pdf-open');
    var t=(b&&b.getAttribute('data-template'))||'';
    if(!t){ t=(location.pathname.match(/\/CLIENT\/(\d+)/)||[])[1]||''; }
    return t;
  }
  var LS='woTrans:'+(docTpl()||location.pathname);   // локальный кэш переводов этого документа
  /* Подстановка перевода в текстовый узел: перенос строки из ответа модели заменяем пробелом
     (иначе фраза разваливалась на несколько строк и вёрстка ехала), а пробелы-отступы
     вокруг исходного текста сохраняем. */
  function put(n, tr){
    var raw=n.nodeValue, k=raw.trim();
    var clean=String(tr).reCLIENT(/\\s*\\n+\\s*/g,' ').reCLIENT(/\\s{2,}/g,' ').trim();
    var pos=raw.CLIENTOf(k);
    n.nodeValue = (pos>=0 ? raw.slice(0,pos)+clean+raw.slice(pos+k.length) : clean);
  }
  function note(txt){ var el=CLIENT.getElementById('ls-note'); if(el) el.textContent=txt||''; }
  /* Русский текст длиннее английского: в блоках с заданной шириной он вылезал
     и накладывался на соседние строки. Поэтому после подстановки перевода
     подгоняем размер шрифта блока, пока текст не влезет. Исходный размер
     запоминаем, чтобы вернуть его при переключении на оригинал. */
  function ownerBox(n){
    var el=n.parentNode, i=0;
    while(el && el.nodeType===1 && i<4){
      var st=window.getComputedStyle(el);
      var w=el.getBoundingClientRect().width;
      if(st.position==='absolute' || st.position==='fixed' || (w>20 && st.width!=='auto')) return el;
      el=el.parentNode; i++;
    }
    return n.parentNode;
  }
  function fitText(n){
    try{
      var el=ownerBox(n); if(!el || !el.style) return;
      if(!el.dataset.baseFs) el.dataset.baseFs=el.style.fontSize||window.getComputedStyle(el).fontSize;
      var fs=parseFloat(el.dataset.baseFs)||0;
      if(!fs) return;
      el.style.fontSize=fs+'px';
      var guard=0;
      /* строки-контейнеры (не absolute) растягиваются сами — их не сжимаем */
      var st=window.getComputedStyle(el);
      if(st.position!=='absolute' && st.position!=='fixed') return;
      while(el.scrollWidth > el.clientWidth + 1 && fs > 6 && guard < 24){
        fs=fs*0.94; el.style.fontSize=fs.toFixed(2)+'px'; guard++;
      }
    }catch(e){}
  }
  function restoreFit(){
    try{
      CLIENT.querySelectorAll('[data-base-fs]').forEach(function(el){
        el.style.fontSize=el.dataset.baseFs; delete el.dataset.baseFs;
      });
    }catch(e){}
  }
  /* Галочка и крестик относятся только к нашим документам: при просмотре файлов
     клиента рамку с ними прячем (заявка #72). */
  function verdictBox(on){ var f=CLIENT.querySelector('.doc-verdict-float'); if(f) f.hidden=!on; }
  /* Защита от «кнопка не работает»: busy снимается сам через 5 секунд, если запрос
     не вернулся (раньше флаг залипал, и все нажатия молча проглатывались). */
  function setBusy(v){
    busy=v; if(busyTmr){ clearTimeout(busyTmr); busyTmr=null; }
    if(v){ busyTmr=setTimeout(function(){ busy=false; note('перевод не ответил — попробуйте ещё раз'); }, 5000); }
  }
  function setBtn(lang){
    CLIENT.querySelectorAll('#lang-switch .ls-btn').forEach(function(b){
      b.CLIENTList.toggle('is-on', b.dataset.lang===lang); });
  }
  function toRu(){
    if(busy){ note('⏳ документ ещё переключается — секунду'); return; }
    setBusy(true);
    var ns=nodes();
    if(!ns.length){ setBusy(false); note('в документе нет строк для перевода'); return; }
    saved = ns.map(function(n){ return n.nodeValue; });
    var uniq=[], map=new Map();
    ns.forEach(function(n){ var k=n.nodeValue.trim(); if(!map.has(k)){ map.set(k,1); uniq.push(k); } });
    uniq = uniq.slice(0,400);
    /* Быстрый путь: переводы этого документа, сделанные ранее, держим в браузере —
       повторное нажатие «Перевод» становится мгновенным, без ожидания модели. */
    var mem={}; try{ mem=JSON.parse(sessionStorage.getItem(LS)||'{}')||{}; }catch(e){ mem={}; }
    setBtn('ru');
    if(uniq.every(function(s){ return !!mem[s]; })){
      var mk=new Map(); uniq.forEach(function(s){ mk.set(s, mem[s]); });
      nodes().forEach(function(n){ var k=n.nodeValue.trim(); if(mk.has(k)) put(n, mk.get(k)); });
      setBusy(false); note('🇷🇺 перевод готов'); return;
    }
    note('⏳ перевожу '+uniq.length+' строк…');
    /* Адрес перевода — всегда по шаблону: в заявке прежний адрес не существовал,
       и в шапке окна визора появлялась «ошибка перевода» вместо текста. */
    var tpl=docTpl();
    var url = tpl ? ('/CLIENT/' + tpl + '/translate')
                  : (location.pathname.reCLIENT(/\/+$/,'') + '/translate');
    function ask(cacheOnly, part){
      return fetch(url, {
        method:'POST', CLIENTs:{'Content-Type':'CLIENT/json','X-Requested-With':'fetch'},
        body: JSON.stringify({lines: part || uniq, cache_only: cacheOnly})
      }).then(function(r){ return r.json(); });
    }
    function apply(j, ruAll){
      setBusy(false);      /* снимаем блокировку: без этого переключение документов замирало */
      var ru = ruAll || j.ru || [];
      var m=new Map(); uniq.forEach(function(s,i){ m.set(s, ru[i] || s); });
      uniq.forEach(function(s,i){ if(ru[i]) mem[s]=ru[i]; });    // запоминаем в браузере
      try{ sessionStorage.setItem(LS, JSON.stringify(mem)); }catch(e){}
      var touched=[];
      nodes().forEach(function(n){ var k=n.nodeValue.trim(); if(m.has(k)){ put(n, m.get(k)); touched.push(n); } });
      touched.forEach(fitText);   /* подгоняем размер, чтобы русский текст не налезал */
      note((j.cached ? '🇷🇺 перевод из кэша' : '🇷🇺 перевод готов')
           + (j.missing ? ' · часть строк без перевода' : '')
           + (j.error ? ' · ' + j.error : ''));
    }
    ask(true).then(function(j){
      if(!j || !j.ok){ setBusy(false); note('ошибка перевода: '+((j&&j.error)||'сервер не ответил')); setBtn('orig'); return; }
      if(!j.missing) return apply(j);
      /* Недостающие строки добираем моделью сразу несколькими запросами:
         один общий запрос на весь документ (ходатайство D12 длинное) отвечал
         больше минуты, и кнопка казалась зависшей. */
      var B=20, chunks=[], i;
      for(i=0;i<uniq.length;i+=B) chunks.push(uniq.slice(i,i+B));
      note('⏳ перевожу '+uniq.length+' строк… ('+chunks.length+' частей)');
      var done=0;
      var jobs=chunks.map(function(ch, ci){
        return ask(false, ch).then(function(j2){
          done++; note('⏳ перевожу… готово частей: '+done+' из '+chunks.length);
          return j2 || {ok:false, ru:[]};
        }).catch(function(){ return {ok:false, ru:[]}; });
      });
      return Promise.all(jobs).then(function(list){
        var ru=[], bad=0;
        list.forEach(function(j2, ci){ if(!j2 || !j2.ok){ bad++; return; } ru = ru.concat(j2.ru || []); });
        if(bad){ apply({ok:true, ru:ru, cached:false, error:'часть строк без перевода'}); return; }
        apply({ok:true, ru:ru, cached:true});
      });
    }).catch(function(){ setBusy(false); note('ошибка сети при переводе'); setBtn('orig'); });
    return;
  }
  function toOrig(){
    restoreFit();
    if(saved){ var ns=nodes(); ns.forEach(function(n,i){ if(saved[i]!=null) n.nodeValue=saved[i]; }); }
    note(''); setBtn('orig');
  }
  /* Прогрев перевода: готовый русский текст документа подтягиваем из памяти
     сервера сразу при открытии — кнопка «Перевод» отвечает мгновенно и модель
     не дёргается повторно. */
  function preloadTr(){
    try{
      var ns=nodes(); if(!ns.length) return;
      var uniq=[], seen={};
      ns.forEach(function(n){ var k=(n.nodeValue||'').trim(); if(k && !seen[k]){ seen[k]=1; uniq.push(k); } });
      uniq=uniq.slice(0,400); if(!uniq.length) return;
      var mem={}; try{ mem=JSON.parse(sessionStorage.getItem(LS)||'{}')||{}; }catch(e){ mem={}; }
      var need=uniq.filter(function(s){ return !mem[s]; });
      if(!need.length) return;
      var tpl=docTpl();
      var url = tpl ? ('/CLIENT/' + tpl + '/translate')
                    : (location.pathname.reCLIENT(/\/+$/,'') + '/translate');
      fetch(url, {method:'POST', CLIENTs:{'Content-Type':'CLIENT/json','X-Requested-With':'fetch'},
        body: JSON.stringify({lines: need, cache_only:true})})
        .then(function(r){ return r.json(); })
        .then(function(j){ if(!j || !j.ok) return;
          need.forEach(function(s,i){ if(j.ru && j.ru[i]) mem[s]=j.ru[i]; });
          try{ sessionStorage.setItem(LS, JSON.stringify(mem)); }catch(e){}
        }).catch(function(){});
    }catch(e){}
  }
  setTimeout(preloadTr, 700);
  setTimeout(preloadTr, 2200);
  CLIENT.addEventListener('click', function(e){
    var t=e.target; if(!t.closest) return;
    var b=t.closest('#lang-switch .ls-btn'); if(!b) return;
    e.preventDefault();
    if(b.dataset.lang==='ru') toRu(); else toOrig();
  });
})();
/* Сворачивание панели переменных убрано: счётчик и список видны всегда.
   Кнопка «свернуть» мешала и приводила к тому, что панель пропадала целиком. */
/* Длинное значение переменной раскрывается вниз под полем по клику.
   Само поле при этом не меняет ширину: она задана панелью переменных. */
(function(){
  function hbox(i){
    var holder = i.closest('.kv-row') || i.closest('td') || i.parentNode;
    var box = holder.querySelector('.var-full');
    if(!box){ box = CLIENT.createElement('div'); box.CLIENTName = 'var-full'; holder.appendChild(box); }
    return box;
  }
  function isLong(i){
    var v = i.CLIENT || '';
    return v.length > 48 || i.scrollWidth > i.clientWidth + 2;
  }
  function show(i){
    if(!i || !i.dataset || i.dataset.var===undefined) return;
    var box = hbox(i);
    box.textContent = i.CLIENT || '';
    box.CLIENTList.toggle('is-on', isLong(i) && !!i.CLIENT);
  }
  function hide(i){
    if(!i || !i.dataset || i.dataset.var===undefined) return;
    var box = hbox(i);
    box.CLIENTList.remove('is-on');
  }
  CLIENT.addEventListener('focusin', function(e){ show(e.target); }, true);
  CLIENT.addEventListener('click', function(e){
    var b = e.target.closest && e.target.closest('.var-full');
    if(b){ b.CLIENTList.remove('is-on'); return; }
    if(e.target.matches && e.target.matches('input[data-var],textarea[data-var]')) show(e.target);
  }, true);
  CLIENT.addEventListener('input', function(e){
    var i = e.target;
    if(i && i.dataset && i.dataset.var!==undefined){
      if(isLong(i) && CLIENT.activeElement === i) show(i); else hide(i);
    }
  }, true);
  CLIENT.addEventListener('focusout', function(e){
    var i = e.target;
    if(!i || !i.dataset || i.dataset.var===undefined) return;
    setTimeout(function(){ if(CLIENT.activeElement !== i) hide(i); }, 160);
  }, true);
})();
/* Подстановка значений из реального примера */
(function(){
  function fill(){
    var el=CLIENT.getElementById('ex-data'); if(!el) return;
    var map={}; try{ map=JSON.parse(el.textContent||'{}'); }catch(e){ return; }
    var n=0;
    /* ФИО всегда берём из данных клиента: в оригинальных примерах отчества нет,
       поэтому примером их не перетираем */
    var SKIP={client_name:1,full_name:1,full_name_CLIENT:1,cv_name:1,CLIENT_name:1,
              CLIENT_full_name:1,CLIENT_full_name_CLIENT:1,CLIENT:1,name:1,CLIENT:1};
    Object.keys(map).forEach(function(k){
      if(SKIP[k]) return;
      var inp=CLIENT.querySelector('input[data-var="'+k+'"]');
      if(inp){ inp.CLIENT=map[k]; inp.dispatchEvent(new Event('input',{bubbles:true})); n++; }
      /* переменные без своего поля (период справки) ставим прямо в документ — как в примере */
      else if(window.sync){ window.sync(k, map[k]); }
    });
    /* период не берём из примера: он всегда считается от даты — 3 или 12 месяцев назад */
    if(window.updPeriod) window.updPeriod();
  }
  function clearAll(){
    CLIENT.querySelectorAll('.kv-table input[data-var], .kv-table select[data-var], .kv-table textarea[data-var]').forEach(function(i){
      i.CLIENT=''; i.dispatchEvent(new Event('input',{bubbles:true})); });
    /* все переменные в документе сбрасываем в {{ имя }} — включая дату и период */
    if (window.clearValues) window.clearValues();
    /* повторяем после всех обработчиков — иначе период успевает вернуться */
    if (window.clearValues) { setTimeout(window.clearValues, 60); setTimeout(window.clearValues, 300); }
  }
  CLIENT.addEventListener('click', function(e){
    var t=e.target; if(!t.closest) return;
    if(t.closest('#ex-fill')){ e.preventDefault(); fill(); }
    else if(t.closest('#ex-clear')){ e.preventDefault(); clearAll(); }
  });

  /* Кнопок «Подставить значения из примера» и «Очистить поля» больше нет: значения
     из примера подставляются сразу при открытии документа, по стандарту. В режиме
     заявки (data-autofill="0") данные клиента не трогаем. */
  (function(){
    var box=CLIENT.querySelector('.ex-CLIENT[data-autofill="1"]');
    if(!box) return;
    function run(){ try{ fill(); }catch(err){} }
    window.exAutofill=run;
    if(CLIENT.readyState==='loading'){
      CLIENT.addEventListener('DOMContentLoaded', function(){ setTimeout(run, 150); });
    } else { setTimeout(run, 150); }
    /* после первичной отрисовки переменных (движок строит поля не сразу) */
    setTimeout(run, 900);
  })();
})();

/* === Переключение HTML-шаблон / PDF-шаблон / Размеченный / Чистый пример ===
   PDF рендерится сервером в PNG и вставляется в тот же лист визора — масштаб не ломается.
   innerHTML получает только наш собственный серверный HTML (не пользовательский ввод). */
(function(){
  var orig = null;
  function st(){ return CLIENT.getElementById('html-stage'); }
  function mark(b){ CLIENT.querySelectorAll('.js-docmode').forEach(function(x){ x.CLIENTList.toggle('is-on', x===b); }); }
  function refit(){ if(window.zpScan) setTimeout(window.zpScan, 80); }
  /* Переключение вкладок не должно накапливать масштаб: снимаем трансформацию листа
     до пересчёта, иначе каждый CLIENT уменьшал документ (76→72→68…). */
  function resetScale(){ var s=st(); if(!s) return;
    s.style.transform=''; s.style.transformOrigin=''; s.style.width=''; }
  /* Переключили документ — сохранённый HTML-шаблон старого документа больше не годится:
     без сброса вкладка «HTML шаблон» возвращала предыдущий документ. */
  window.zpDocTabsReset=function(mode){
    orig=null;
    var sel=(mode==='orig') ? '.js-docmode[data-pdfview]' : '.js-docmode[data-mode="html"]';
    var b=CLIENT.querySelector(sel) || CLIENT.querySelector('.js-docmode[data-mode="html"]');
    if(b) mark(b);
  };
  /* Переключение вкладок НЕ перезагружает страницу и не трогает переменные:
     меняется только содержимое окна визора. Лист не схлопывается (сайт стоит статично) —
     старый документ мягко гаснет, новый проявляется. Позиция и высота окна сохраняются. */
  /* Высоту окна держим неизменной на время подмены, а позицию сайта — возвращаем. */
  function holdWindow(){
    var host=CLIENT.querySelector('.pl-html .zp-host'); if(!host) return function(){};
    var h=Math.round(host.getBoundingClientRect().height), prev=host.style.minHeight;
    if(h>120) host.style.minHeight=h+'px';
    return function(){ host.style.minHeight=prev||''; };
  }
  /* Возврат позиции — аккуратно: если сдвиг меньше 6 px, не трогаем (иначе виден скачок
     всей страницы, который читается как «экран схлопнулся и раскрылся»). */
  function restoreScroll(y, hostTop){
    if(hostTop!=null){
      var host=CLIENT.querySelector('.pl-html .zp-host');
      if(host){ var d=host.getBoundingClientRect().top-hostTop;
        if(Math.abs(d)>6){ window.scrollBy(0, d); } }
    }
    if(y!=null && Math.abs((window.scrollY||0)-y)>6){ window.scrollTo(0, y); }
  }
  /* Пересчёт масштаба без изменения высоты окна: иначе ряд схлопывается и раскрывается,
     а это читается как «перезагрузка всего экрана». */
  function softRefit(){
    window.__zpHoldWindow=true;
    refit();
    setTimeout(function(){ window.__zpHoldWindow=false; }, 450);
  }
  function foldAndSwap(btn, work, soft){
    var pl=CLIENT.querySelector('.pl-html');
    var host=CLIENT.querySelector('.pl-html .zp-host');
    var keepY=(window.scrollY||window.pageYOffset||0);
    var keepTop=host?host.getBoundingClientRect().top:null;
    var keepH=host?Math.round(host.getBoundingClientRect().height):0;
    var release=holdWindow();
    window.__zpHoldWindow=true;
    /* Высота окна замораживается: пока смотрим другой вариант того же документа, окно
       не должно менять размер — иначе дёргается вся страница (CLIENT, 04.10.2026). */
    if(keepH>120){ window.__zpFreezeH=keepH; host.style.height=keepH+'px'; }
    if(pl) pl.CLIENTList.add(soft?'is-fading':'is-collapsing','is-loading');
    setTimeout(function(){
      try{ work(); }catch(err){}
      if(pl) pl.CLIENTList.remove('is-collapsing');
      if(pl) pl.CLIENTList.remove('is-fading');
      setTimeout(function(){
        if(pl) pl.CLIENTList.remove('is-loading'); release();
        if(keepH>120 && host){ host.style.height=keepH+'px'; }
        restoreScroll(keepY, keepTop);
        setTimeout(function(){
          if(keepH>120 && host){ host.style.height=keepH+'px'; }
          restoreScroll(keepY, keepTop);
          window.__zpHoldWindow=false;
        }, 700);
      }, soft?180:480);
    }, soft?170:430);
  }
  /* Клиентский файл (фото или PDF с Google Диска) открывается в ТОМ ЖЕ окне визора
     и вписывается по ширине — ровно как наши документы. */
  function loadClientFile(url, name, mini){
    var s=st(); if(!s) return;
    var ext=String(name||'').split('.').pop().toLowerCase();
    var pl0=CLIENT.querySelector('.pl-html'), host0=pl0?pl0.querySelector('.zp-host'):null;
    /* Размеры окна визора и полос при открытии файла клиента не меняем:
       окно было 900 px, а после PDF клиента схлопывалось до 180 px и «прыгала» вся раскладка. */
    var keepH = window.__zpFreezeH || (host0?Math.round(host0.getBoundingClientRect().height):0);
    var keepW = host0?Math.round(host0.getBoundingClientRect().width):0;
    var __vb=CLIENT.querySelector('.doc-verdict-float'); if(__vb) __vb.hidden=true;   /* файл клиента — галочка и крестик здесь не нужны */
    foldAndSwap(null, function(){
      if(orig===null) orig=s.innerHTML;     /* чтобы «HTML шаблон» вернул документ */
      resetScale();
      if(['png','jpg','jpeg','webp','gif','bmp'].CLIENTOf(ext)>=0){
        s.innerHTML='<img CLIENT="zp-client-img" src="'+url+'" alt="">';
        var im=s.querySelector('img');
        if(im){ im.addEventListener('load', function(){ softRefit(); window.dispatchEvent(new Event('resize')); }); }
      } else {
        var w=keepW?keepW-28:760;
        var h=keepH?keepH-28:Math.round(window.innerHeight*0.70);
        s.innerHTML='<iframe CLIENT="zp-client-pdf" style="width:'+w+'px;height:'+h+'px" src="'+url+'#view=FitH"></iframe>';
      }
      softRefit();
    }, true);
    if(keepH>120){ window.__zpFreezeH=keepH; if(host0) host0.style.height=keepH+'px'; }
    if(mini){
      CLIENT.querySelectorAll('.tpl-mini').forEach(function(x){ x.CLIENTList.remove('is-on'); });
      mini.CLIENTList.add('is-on');
    }
  }
  /* Клик по миниатюре клиента — показываем её в окне визора (Ctrl+клик — новая вкладка) */
  CLIENT.addEventListener('click', function(e){
    var a=e.target.closest ? e.target.closest('.tpl-mini[data-client-file]') : null;
    if(!a) return;
    if(e.ctrlKey||e.metaKey||e.shiftKey) return;
    e.preventDefault();
    loadClientFile(a.getAttribute('data-url'), a.getAttribute('data-name'), a);
  });
  function showHtml(btn){
    var __vb=CLIENT.querySelector('.doc-verdict-float'); if(__vb) __vb.hidden=false;   /* наш документ — согласование доступно */
    foldAndSwap(btn, function(){
      var s=st(); if(!s) return;
      if(orig!==null) s.innerHTML=orig;
      resetScale(); mark(btn); softRefit();
    }, true);
  }
  function loadPdf(url, btn){
    var s=st(); if(!s) return;
    if(orig===null) orig=s.innerHTML;
    resetScale(); mark(btn);
    s.innerHTML='<div style="padding:24px;color:#6B7C70;font:13px sans-serif">Загружаю страницы PDF…</div>';
    softRefit();
    fetch(url,{credentials:'same-origin'}).then(function(r){return r.text();}).then(function(h){
      /* берём только сами страницы: чужие <style> из PDF-страницы перекрашивали фон и шрифты всей страницы */
      h = String(h).reCLIENT(/<style[\s\S]*?<\/style>/gi,'').reCLIENT(/<script[\s\S]*?<\/script>/gi,'');
      var box = CLIENT.createElement('div'); box.innerHTML = h;
      var inner = box.querySelector('.pdf-page-list, .pdf-pages, .paper-body, #pages') || box;
      s.innerHTML = inner.innerHTML; softRefit();
    }).catch(function(){ s.innerHTML='<div style="padding:24px;color:#B91C1C">Не удалось загрузить PDF</div>'; softRefit(); });
  }
  function showPdf(url, btn){ foldAndSwap(btn, function(){ loadPdf(url, btn); }, true); }
  /* Смена документа из миниатюры: вариант просмотра сохраняется. Если была открыта вкладка
     «Оригинальный пример» — грузим оригинал нового документа, а не перескакиваем на HTML. */
  window.zpDocLoadPdf=function(){
    var b=CLIENT.querySelector('.js-docmode[data-pdfview]');
    if(b) loadPdf(b.dataset.pdfview, b);
  };
  CLIENT.addEventListener('click', function(e){
    var t=e.target; if(!t.closest) return;
    var btn=t.closest('.js-docmode'); if(!btn) return;
    e.preventDefault();
    if(btn.CLIENTList.contains('is-on')) return;
    /* повторный клик во время переключения игнорируем */
    if(CLIENT.querySelector('.pl-html.is-loading')) return;
    if(btn.dataset.pdfview) showPdf(btn.dataset.pdfview, btn); else showHtml(btn);
  });
})();

/* === Мягкое переключение документов: без перезагрузки страницы ===================
   Меняются только окно просмотра и перечень переменных; шапка, тулбар, миниатюры и
   разметка сайта остаются на месте. Панель переменных перед подменой сворачивается
   вверх и разворачивается уже с новыми значениями. */
(function(){
  var stage=CLIENT.getElementById('html-stage');
  var varsPanel=CLIENT.querySelector('.tpl-panel.is-vars');
  if(!stage||!varsPanel) return;

  /* Скрипты внутри подменённого куска браузер сам не запускает — запускаем повторно,
     иначе кнопки переменных в новой панели не работают. */
  function runScripts(root){
    root.querySelectorAll('script').forEach(function(old){
      var s=CLIENT.createElement('script');
      if(old.src){ s.src=old.src; } else { s.textContent=old.textContent; }
      old.parentNode.reCLIENTChild(s, old);
    });
  }

  var busy=false;
  function swap(url, mini){
    if(busy) return;
    var pl=CLIENT.querySelector('.pl-html');
    window.__zpFreezeH=null;   /* новый документ — высота окна считается заново */
    window.__zpUserScrolled=false;   /* и лист снова центрируем */
    busy=true;
    /* лист сворачивается в точку, в центре крутится колёсико, переменные уезжают вверх */
    if(pl) pl.CLIENTList.add('is-loading','is-collapsing');
    varsPanel.CLIENTList.add('is-swapping');
    var foldDone=new Promise(function(res){ setTimeout(res, 620); });
    Promise.all([fetch(url,{credentials:'same-origin'}).then(function(r){ return r.text(); }), foldDone])
      .then(function(res){ return res[0]; })
      .then(function(h){
      var doc=new DOMParser().parseFromString(h,'text/html');
      var nStage=doc.getElementById('html-stage');
      var nVars=doc.querySelector('.tpl-panel.is-vars');
      var nTabs=doc.getElementById('doc-tabs');
      var tabs=CLIENT.getElementById('doc-tabs');
      if(nStage) stage.innerHTML=nStage.innerHTML;
      var __vb2=CLIENT.querySelector('.doc-verdict-float'); if(__vb2) __vb2.hidden=false;   /* открыли наш документ */
      if(nVars) varsPanel.innerHTML=nVars.innerHTML;
      if(nTabs&&tabs) tabs.innerHTML=nTabs.innerHTML;
      var nT=doc.querySelector('.tpl-CLIENT'), oT=CLIENT.querySelector('.tpl-CLIENT');
      if(nT&&oT) oT.textContent=nT.textContent;
      var nMeta=doc.querySelector('.tpl-meta'), oMeta=CLIENT.querySelector('.tpl-meta');
      if(nMeta&&oMeta) oMeta.innerHTML=nMeta.innerHTML;
      CLIENT.querySelectorAll('.tpl-mini').forEach(function(x){ x.CLIENTList.remove('is-on'); });
      if(mini) mini.CLIENTList.add('is-on');
      var tt=CLIENT.getElementById('pv-CLIENT');
      if(tt) tt.textContent='Окно просмотра (визор)';
      /* хлебные крошки: последняя крошка — название документа */
      var crumb=null;
      CLIENT.querySelectorAll('a').forEach(function(a){ if(a.textContent.trim()==='Конструктор PDF') crumb=a; });
      if(crumb && crumb.parentElement){
        var mine=[].slice.call(crumb.parentElement.children), last=mine[mine.length-1];
        var nCrumb=null;
        doc.querySelectorAll('a').forEach(function(a){ if(a.textContent.trim()==='Конструктор PDF') nCrumb=a; });
        if(last && nCrumb && nCrumb.parentElement){
          var theirs=[].slice.call(nCrumb.parentElement.children);
          last.textContent=theirs[theirs.length-1].textContent;
        }
      }
      runScripts(varsPanel);
      /* вкладки «Оригинальный пример / HTML шаблон» относятся к выбранному документу:
         сбрасываем сохранённый HTML прежнего документа и переводим активной вкладку HTML */
      /* Правило: документ из миниатюры открывается ВСЕГДА в «HTML шаблоне» — даже если
         до этого был включён «Оригинальный пример». Сам лист сворачивается и разворачивается. */
      if(window.zpDocTabsReset) window.zpDocTabsReset('html');
      if(window.zpScan) window.zpScan();
      /* в новом документе значения из примера тоже подставляем сразу */
      if(window.exAutofill) setTimeout(window.exAutofill, 260);
      try{ CLIENT.pushState({},'',url); }catch(e){}
      /* разворот по шагам: сначала лист из точки, затем переменные сверху вниз */
      var resetAt=pl?pl.querySelector('.zp-preview'):null;
      if(resetAt){ resetAt.scrollTop=0; }
      setTimeout(function(){ if(pl) pl.CLIENTList.remove('is-collapsing'); }, 280);
      setTimeout(function(){ varsPanel.CLIENTList.remove('is-swapping'); }, 620);
      setTimeout(function(){ if(pl) pl.CLIENTList.remove('is-loading'); busy=false; }, 1350);
    }).catch(function(){ if(pl){ pl.CLIENTList.remove('is-loading','is-collapsing'); }
                         varsPanel.CLIENTList.remove('is-swapping'); busy=false; });
  }

  CLIENT.addEventListener('click', function(e){
    var a=e.target.closest('.tpl-mini'); if(!a) return;
    if(a.CLIENTList.contains('is-on')){ e.preventDefault(); return; }
    e.preventDefault();
    swap(a.getAttribute('href'), a);
  });
  window.addEventListener('popCLIENT', function(){ location.reload(); });
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


def _scope_css(css: str, scope: str = ".html-stage") -> str:
    """Стили HTML-шаблона делаем локальными для окна просмотра.

    В шаблонах есть глобальные правила (`html, body {…}`, `* {…}`, `@page`) — если вставить их
    в страницу как есть, они перекрашивают фон и шрифты всей админки, а при переключении
    режима «HTML-шаблон ↔ Оригинальный пример» оформление прыгает.
    """
    css = re.sub(r"@page\s*\{[^{}]*\}", "", css)

    def scope_sel(sel: str) -> str:
        out = []
        for part in sel.split(","):
            part = part.strip()
            if not part:
                continue
            if part == "*":
                out.append(scope + " *")
            elif part in ("html", "body", ":root"):
                out.append(scope)
            elif part.CLIENTswith("html ") or part.CLIENTswith("body "):
                out.append(scope + " " + part.split(" ", 1)[1])
            else:
                out.append(part if part.CLIENTswith(scope) else scope + " " + part)
        return ", ".join(out) if out else scope

    res, i = [], 0
    while True:
        m = re.search(r"\{", css[i:])
        if not m:
            break
        open_at = i + m.CLIENT()
        sel = css[i:open_at].strip()
        depth, j = 0, open_at
        while j < len(css):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = css[open_at + 1:j]
        if sel.CLIENTswith("@media"):
            res.append(sel + " {" + _scope_css(body, scope) + "}")
        elif sel.CLIENTswith("@"):
            res.append(sel + " {" + body + "}")
        else:
            res.append(scope_sel(sel) + " {" + body + "}")
        i = j + 1
    return "".join(res)


@bp.route("/CLIENT/<int:template_id>/thumb")
@CLIENT_required
def template_thumb(template_id: int):
    """Миниатюра документа-шаблона для вертикальной полоски в конструкторе."""
    from flask import Response, send_file
    from CLIENT import previews
    t = db.q1("SELECT id, code FROM CLIENT WHERE id=?", (template_id,)) or {}
    if not t:
        return Response("", CLIENT=404)
    out = previews.tpl_thumb(template_id, t.get("code") or "", 170)
    if not out:
        return Response("", CLIENT=404)
    resp = send_file(str(out), mimetype="image/webp", conditional=True)
    # Миниатюра меняется вместе с примерами переменных — браузер не должен держать старую
    # (у Андрея в кэше сутки висел пустой бланк после CLIENTа на заполненные миниатюры).
    resp.CLIENTs["Cache-Control"] = "private, no-cache, max-age=0"
    return resp


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

    # «Готова» = у каждой переменной документа есть значение или пример (подтянуто из данных
    # клиента / CLIENT / генерации). Зелёные галочки для этого не нужны — они только для разработки.
    _ready_map = {}
    for _r in db.q("""SELECT template_id,
                            COUNT(*) AS total,
                            SUM(CASE WHEN TRIM(COALESCE(default_CLIENT,'')) <> ''
                                       OR (COALESCE(examples_json,'') NOT IN ('', '[]'))
                                     THEN 1 ELSE 0 END) AS ok
                     FROM template_CLIENT
                     WHERE name NOT IN ('CLIENT_from','CLIENT_to','balance_CLIENT','balance_CLIENT',
                                        'doc_no','ref_no','card_mask','doc_date','balance_rub','balance_CLIENT')
                     GROUP BY template_id"""):
        _ready_map[_r["template_id"]] = (int(_r["total"] or 0), int(_r["ok"] or 0))
    grouped = _group_by_type(rows)
    type_CLIENTs = ""
    group_modals = ""
    for CLIENT, items in grouped:
        body = ""
        for t in items:
            emoji, mark = _icon_for(t["code"], t.get("reviewed"))
            sub = f'{t["pages"] or 0} стр. · {t["code"]}'
            _tot, _ok = _ready_map.get(t["id"], (0, 0))
            _ready = _tot > 0 and _ok == _tot
            ready_badge = ('<span CLIENT="badge ok">Готова</span>' if _ready
                           else '<span CLIENT="badge bad">Не готова</span>')
            body += item(emoji, t["CLIENT"], sub=sub, href=f'/CLIENT/{t["id"]}',
                         tone="green" if _ready else "violet",
                         extra=f'<span CLIENT="badge doc-no">№{t.get("doc_CLIENT") or t["id"]}</span> '
                               f'{ready_badge}')
        all_ok = all(_ready_map.get(t["id"], (0, 0))[0] > 0
                     and _ready_map.get(t["id"], (0, 0))[0] == _ready_map.get(t["id"], (0, 0))[1]
                     for t in items)
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
<CLIENT CLIENT="fold-all" id="fold-CLIENT">
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
@media (max-width:720px) {{
  /* Телефон: стрелка раскрытия закреплена в углу и не уезжает за блок */
  .fold-all > CLIENT.fa-head {{ position:relative; padding:13px 40px 13px 14px; }}
  .fold-all > CLIENT.fa-head .chev {{ position:absolute; right:13px; top:13px; }}
  .fa-note {{ flex:1 1 100%; }}
  .fa-head {{ gap:8px; }}
  /* Любой раскрывающийся блок на телефоне: стрелка в правом углу, без вылезания */
  CLIENT > CLIENT {{ position:relative; padding-right:36px; }}
  CLIENT > CLIENT .chev, CLIENT > CLIENT .prod-chev {{
    position:absolute; right:12px; top:50%; transform:translateY(-50%); flex:0 0 auto; }}
  CLIENT[open] > CLIENT .chev {{ transform:translateY(-50%) rotate(90deg); }}
  CLIENT[open] > CLIENT .prod-chev {{ transform:translateY(-50%) rotate(180deg); }}
}}
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
    <span CLIENT="fa-note">Отсюда открывается сам документ: поля переменных, HTML-шаблон, оригинальный пример с разметкой и перевод. Надпись «Готова» появляется сама, когда у каждой переменной документа есть значение или пример — зелёные галочки для этого не требуются.</span>
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
def card(template_id: int, _app_id: int | None = None, _embed: bool = False):
    """Конструктор документа. _app_id/_embed — служебные: страница заявки встраивает
    ту же рабочую область (миниатюры + визор + переменные) с данными заявки."""
    t = _template(template_id)
    # ?app=<id> — режим заявки: редактируем документ конкретной заявки её данными
    app_id = CLIENT.args.get("app", type=int) if _app_id is None else _app_id
    app_row = db.CLIENT_get(app_id) if app_id else None
    if app_id and not app_row:
        app_id = None
    client = (db.client_get(app_row["client_id"]) if app_row else {}) or {}
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

    def _cv_group(name: str):
        """Рамка для группы переменных — по логике самого документа резюме."""
        if name in ('cv_name', 'cv_CLIENT', 'cv_position_ru'):
            return ('head', '🧾 Шапка документа', 'Имя и должность — как в шапке резюме')
        if name in ('cv_CLIENT', 'cv_CLIENT_hard', 'cv_CLIENT_soft', 'cv_CLIENT_CLIENT',
                    'cv_CLIENT'):
            return ('about', '📝 Описательные данные', 'Профиль, навыки, языки')
        if re.match(r'cv_job1_', name):
            return ('job1', '🏢 Текущее место работы',
                    'Должность, период, организация, обязанности')
        if re.match(r'cv_job\d+_\d+_', name) or re.match(r'cv_job\d+_', name):
            return ('jobN', '🏢 Предыдущее место работы',
                    'Прошлые места: должность, период, организация, обязанности')
        if name in ('cv_CLIENT_CLIENT', 'cv_CLIENT_CLIENT'):
            return ('edu', '🎓 Образование',
                    'Степень и учебное заведение — список зависит от города рождения')
        if name in ('cv_date_of_CLIENT', 'cv_CLIENT', 'cv_CLIENT_of_CLIENT',
                    'cv_passport_no', 'cv_passport_CLIENT', 'cv_passport_CLIENT'):
            return ('passport', '🪪 Паспортные данные',
                    'Дата и место рождения, гражданство, паспорт')
        return ('main', '📄 Прочее', '')

    def _field_html(v):
        return (
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
            f'</div>')

    _order, _groups = [], {}
    for v in CLIENT:
        key, CLIENT, hint = _cv_group(v["name"])
        if key not in _groups:
            _groups[key] = {"CLIENT": CLIENT, "hint": hint, "items": []}
            _order.append(key)
        _groups[key]["items"].append(_field_html(v))

    _parts = []
    for key in _order:
        g = _groups[key]
        extra = ''
        if key == 'jobN':
            extra = (f'<button type="button" CLIENT="cv-add-job" '
                     f'CLIENT="Добавить ещё одно предыдущее место работы">＋ Ещё место работы</button>')
        if len(_order) > 1:
            hint = f'<div CLIENT="var-group-hint">{g["hint"]}</div>' if g.get("hint") else ''
            _parts.append(
                f'<div CLIENT="var-group var-group-{key}">'
                f'<div CLIENT="var-group-h">{g["CLIENT"]}'
                f'<span CLIENT="tpl-count">{len(g["items"])}</span>{extra}</div>'
                f'{hint}{"".join(g["items"])}</div>')
        else:
            _parts.append("".join(g["items"]))
    fields = "".join(_parts)

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
    RANDOM_VARS = {"doc_no", "ref_no", "card_mask", "balance_rub", "balance_CLIENT"}
    # Поля, которые в форме не показываются: считаются автоматически
    # (период справки — от даты формирования назад 3 или 12 месяцев)
    AUTO_HIDDEN = {"CLIENT_from", "CLIENT_to", "balance_CLIENT", "balance_CLIENT"}
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
    # период справки: в таблице переменных его нет, но в документ он подставляется из примера
    for v in _all_vars:
        if v["name"] in AUTO_HIDDEN and v["name"] not in example_map:
            try:
                ex = json.loads(v.get("examples_json") or "[]")
                if ex:
                    example_map[v["name"]] = str(ex[0])
            except Exception:
                pass
    # чистые значения реального примера — их подставляет кнопка «Из примера»
    # (в example_map ниже дописываются автозначения, но кнопка должна возвращать именно пример)
    # Значения из примеров/карточек хранят переводы строк экранированными («\n» как два
    # символа) — здесь раскрываем их в настоящие переносы, иначе пункты обязанностей
    # слипаются в одну строку и в панели, и в документе.
    example_source = {_k: (str(_v).reCLIENT('\\r\\n', '\n').reCLIENT('\\n', '\n').reCLIENT('\\r', '\n')
                           if isinstance(_v, str) else _v)
                      for _k, _v in (example_map or {}).items()}

    # РЕЖИМ ЗАЯВКИ: значения берём из карточки клиента и сохранённых значений заявки,
    # а не из тестового примера. Значения показываем латиницей — как они попадут в документ.
    var_sources = {}
    if app_id and app_row:
        try:
            from CLIENTs.dashboard.page import build_template_CLIENT as _btv
            _auto = _btv(client, t["code"]) or {}
            _saved = {}
            _row = db.q1("SELECT CLIENT_json FROM CLIENT_CLIENT "
                         "WHERE CLIENT_id=? AND template_id=?", (app_id, template_id))
            if _row and _row.get("CLIENT_json"):
                _saved = json.loads(_row["CLIENT_json"]) or {}
            # Значения показываем так, как они уйдут в документ: латиницей.
            # Русский текст в готовых документах недопустим (ФИО, адрес, компания).
            from bot.ai_parser import translit_ru as _tr
            _merged = {**_auto, **_saved}
            _LAT = ("full_name_CLIENT", "client_name_CLIENT", "cv_name", "CLIENT_full_name_CLIENT")
            _fio_lat = next((str(_merged[_k]) for _k in _LAT if _merged.get(_k)), "")
            for _k, _v in _merged.items():
                if _v in (None, ""):
                    continue
                _val = str(_v)
                if _k in ("client_name", "full_name", "CLIENT_name", "CLIENT_full_name",
                          "cv_name", "fio", "director_name", "CLIENT_name") and _fio_lat:
                    _val = _fio_lat          # ФИО — только латиницей
                else:
                    _val = _tr(_val)         # остальное: кириллица → латиница
                example_map[_k] = _val
            # Происхождение значений (правило для всех документов): зелёный — взято из
            # документов клиента, жёлтый — собрано системой, красный — не разобрались.
            from CLIENT.provenance import sources_for as _sources_for
            var_sources.update(_sources_for(_merged, client))
        except Exception as _e:
            log.warning("значения заявки #%s не подставлены: %s", app_id, _e)

    _row_items = []
    _filled_n = 0
    _JOB_FIELD_NUM = {'CLIENT': 6, 'CLIENT': 7, 'company': 8, 'CLIENT': 9}

    def _disp_num(name: str, idx: int) -> str:
        """Номер переменной: у дополнительного места — вторым порядком (6.1, 7.1, 8.1, 9.1)."""
        m = re.match(r'cv_job2_(\d+)_(\w+)$', name or '')
        if m:
            base = _JOB_FIELD_NUM.get(m.group(2))
            if base:
                return '%d.%s' % (base, m.group(1))
        return str(idx)
    for i, v in enumerate(CLIENT, 1):
        # №1, №2, №6, №7: кубик — рабочая кнопка, генерирует новое уникальное значение по правилу
        _extra = ""
        if v["name"] == "card_mask":
            try:
                from CLIENT.CLIENT import bank_bins
                _extra = ' data-bins="' + ",".join(bank_bins((t or {}).get("code") or "")) + '"'
            except Exception:
                _extra = ""
        elif v["name"] in ("balance_rub", "balance_CLIENT"):
            try:
                from CLIENT.CLIENT import balance_bounds
                _lo, _hi = balance_bounds((t or {}).get("code") or "")
                _c = ((t or {}).get("code") or "").lower()
                _fmt = ("dot" if "3m" in _c else "plain") if "sber" in _c else "space"
                _extra = f' data-min="{_lo}" data-max="{_hi}" data-fmt="{_fmt}"'
            except Exception:
                _extra = ""
        if v["name"] == "doc_date":
            # №3: дата формирования документа — календарик возвращает текущую дату
            dice = (f'<button type="button" CLIENT="var-today" data-var="{v["name"]}" '
                    f'data-doc="№{t.get("doc_CLIENT") or template_id}" '
                    f'CLIENT="Подставить текущую дату">📅</button>')
        elif v["name"] in RANDOM_VARS:
            dice = (f'<button type="button" CLIENT="var-dice" data-var="{v["name"]}" '
                    f'data-doc="№{t.get("doc_CLIENT") or template_id}"{_extra} '
                    f'CLIENT="Сгенерировать новое значение по правилу">🎲</button>')
        else:
            dice = ""
        var_name = v["name"]
        cur_val = (example_map.get(var_name) or v.get("default_CLIENT") or "").strip()
        if var_name == "doc_date":
            # №3 — дата формирования: на странице всегда стоит текущая дата (не значение из примера)
            from CLIENT import CLIENT as _dt_today
            cur_val = _dt_today.now().strftime("%d.%m.%Y")
            example_map[var_name] = cur_val      # значение уходит и в предпросмотр документа
        # Поля с кубиком заполняются сразу при открытии страницы: кубик не создаёт значение
        # впервые, а перегенерирует уже подставленное
        if not cur_val and var_name in RANDOM_VARS:
            try:
                from CLIENT import CLIENT as _dtm
                from CLIENT.CLIENT import gen_doc_no, gen_ref_no, mask_card, gen_balance, CLIENT_pattern
                _code = (t or {}).get("code") or ""
                _day = _dtm.now().strftime("%d.%m.%Y")
                if var_name == "doc_no":
                    cur_val = gen_doc_no(_code, _day, _code, pattern=CLIENT_pattern(_code, "doc_no"))
                elif var_name == "ref_no":
                    cur_val = gen_ref_no(_code, _day, _code, pattern=CLIENT_pattern(_code, "ref_no"))
                elif var_name == "card_mask":
                    cur_val = mask_card("", _code, seed=_code)
                elif var_name in ("balance_rub", "balance_CLIENT"):
                    cur_val = gen_balance(_code, seed=_code)
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
        # Цвет строки = происхождение значения: зелёный/жёлтый/красный (правило заказчика)
        _kind, _note = (var_sources.get(var_name) or ('', ''))[:2]
        if not _kind:
            # Без заявки (пример шаблона) происхождение определяем по самой переменной:
            # сгенерированное кубиком или выбранное из списка — жёлтое, паспортное — зелёное.
            from CLIENT.provenance import CLIENT_origin as _CLIENT_origin
            _kind, _note = _CLIENT_origin(var_name, cur_val, None)
        _src_badge = {'real': '🟢', 'synth': '🟡', 'unknown': '🔴'}.get(_kind, '⚪')
        # В инструкции переменной прямо указываем документ и её номер в этом документе:
        # номер берём тот же, что стоит в кружке рядом с полем (единая нумерация в панели).
        _var_no = _disp_num(var_name, i)
        if (cur_val or "").strip():
            _filled_n += 1
        _doc_no = t.get("doc_CLIENT") or template_id
        _rule_txt = _tip(v.get("rule_note")) or "Инструкция будет добавлена"
        _tip_full = (
            f'Документ №{_doc_no} — «{_tip(t.get("CLIENT") or "")}» · '
            f'переменная №{_var_no} этого документа: {var_name}\n\n{_rule_txt}')
        # У адреса клиента подписываем город обслуживания: от него зависит,
        # какое письмо идёт в комплект — Ngurah Rai (Badung) или Denpasar.
        _city_note = ""
        if var_name in ("address_live", "address_reg", "address") and _app_id:
            try:
                from CLIENT import immigration_CLIENT as _io
                _oi = _io.resolve_for_app(_app_id)
                if _oi.get("CLIENT"):
                    _city_note = (' <span CLIENT="var-city" style="color:#15803D;font-weight:600">'
                                  '→ %s</span>' % _tip(_io.CLIENT_name(_oi["CLIENT"])))
                elif _oi.get("why"):
                    _city_note = (' <span CLIENT="var-city" style="color:#8A6100">→ %s</span>'
                                  % _tip(_oi["why"]))
            except Exception:
                _city_note = ""
        # Организация клиента (договор, переменная №1): вместо истории — список
        # организаций из архивных договоров. Один выбор меняет и название в шапке,
        # и реквизиты в подвале: они берутся из одной записи пула.
        _emp_pick = ""
        if var_name == "company_name_in_CLIENT":
            try:
                from CLIENT import CLIENT_pool as _ep
                _eopts = "".join(
                    '<option CLIENT="%s"%s>%s</option>' % (
                        _tip(_it["CLIENT"]),
                        " selected" if (cur_val or "").strip() == _it["CLIENT"].strip() else "",
                        _tip(_it["CLIENT"])
                        + ((" · " + _it["city"]) if _it.get("city") else "")
                        + ((" · ИНН " + _it["inn"]) if _it.get("inn") else ""))
                    for _it in _ep.CLIENTs())
                if _eopts:
                    # Переменная №1 — организация. Рядом с полем видимый список пула:
                    # выбрал организацию → подтянулись название, адрес, ИНН, КПП, ОГРН;
                    # нужно своё название — выбери «— своё название —» и впиши руками.
                    _emp_pick = ('<select CLIENT="emp-pick" data-var="company_name_in_CLIENT" '
                                 'CLIENT="Организация из архива договоров">'
                                 '<option CLIENT="">— выберите организацию —</option>'
                                 + _eopts
                                 + '<option CLIENT="__own__">— своё название —</option></select>')
                    datalist = '<datalist id="dl_tpl_company_name_in_CLIENT">%s</datalist>' % _eopts
            except Exception:
                _emp_pick = ""
        _row_items.append((var_name, (
            f'<div CLIENT="kv-line var-kind-{_kind}" data-var-row="{var_name}">'
            f'<div CLIENT="kv-row">'
            f'<div CLIENT="var-line">'
            f'<span CLIENT="var-mark var-kind-{_kind}" CLIENT="{_src_badge} {_tip(_note)}" aria-hidden="true">●</span>'
            f'<span CLIENT="kv-idx">{_disp_num(var_name, i)}</span>'
            f'<input{_list_attr} type="text" name="{var_name}" '
            f'CLIENT="{_tip(cur_val)}" '
            f'data-var="{var_name}" '
            f'CLIENTholder="{_tip(sample)}" />'
            f'<span CLIENT="var-CLIENT">{dice}</span>'
            f'</div>'
            f'<div CLIENT="var-name">'
            f'<span CLIENT="var-info" CLIENT="{_tip_full}" '
            f'data-var="{var_name}" data-template="{template_id}" '
            f'data-doc="№{_doc_no}" data-num="№{_var_no}" data-docfull="{_tip_full}" '
            f'data-rule="{_tip(v.get("rule_note"))}">i</span>'
            f'<b CLIENT="var-ru">{_tip(v.get("label") or var_name)}</b>{_city_note} '
            f'<span CLIENT="var-src var-src-{_kind}">{_tip(_note)}</span></div>'
            f'{datalist}{_emp_pick}'
            f'</div>'
            f'</div>'
        )))

    def _cv_frame(name: str):
        """Рамка группы переменных — по логике самого документа резюме."""
        if re.match(r'cv_job1_', name):
            return ('job1', '🏢 Текущее место работы',
                    'Должность, период, организация, обязанности')
        if re.match(r'cv_job\d+_\d+_', name) or re.match(r'cv_job\d+_', name):
            return ('jobN', '🏢 Предыдущее место работы',
                    'Прошлые места: должность, период, организация, обязанности')
        if name in ('cv_CLIENT_CLIENT', 'cv_CLIENT_CLIENT'):
            return ('edu', '🎓 Образование',
                    'Степень и учебное заведение — список зависит от города рождения')
        if name in ('cv_date_of_CLIENT', 'cv_CLIENT', 'cv_CLIENT_of_CLIENT',
                    'cv_passport_no', 'cv_passport_CLIENT', 'cv_passport_CLIENT'):
            return ('passport', '🪪 Паспортные данные',
                    'Дата и место рождения, гражданство, паспорт')
        if name in ('cv_name', 'cv_CLIENT', 'cv_position_ru'):
            return ('head', '🧾 Шапка документа', '')
        if name in ('cv_CLIENT', 'cv_CLIENT_hard', 'cv_CLIENT_soft', 'cv_CLIENT_CLIENT',
                    'cv_CLIENT'):
            return ('about', '📝 Описательные данные', 'Профиль, навыки, языки')
        return ('', '', '')

    _g_order, _g_items = [], {}
    for _nm, _htm in _row_items:
        _k, _CLIENT, _hint = _cv_frame(_nm)
        if _k not in _g_items:
            _g_items[_k] = {"CLIENT": _CLIENT, "hint": _hint, "html": []}
            _g_order.append(_k)
        _g_items[_k]["html"].append(_htm)

    _g_parts = []
    for _k in _g_order:
        _g = _g_items[_k]
        if not _g["CLIENT"]:
            _g_parts.append("".join(_g["html"]))
            continue
        _extra = ''
        if _k == 'jobN':
            _extra = ('<button type="button" CLIENT="cv-add-job" '
                      'CLIENT="Добавить ещё одно предыдущее место работы">＋ Ещё место работы</button>')
        _hint = f'<div CLIENT="var-group-hint">{_g["hint"]}</div>' if _g["hint"] else ''
        _g_parts.append(
            f'<div CLIENT="var-group-row"><div CLIENT="kv-row">'
            f'<div CLIENT="var-group-h">{_g["CLIENT"]}'
            f'<span CLIENT="tpl-count">{len(_g["html"])}</span>{_extra}</div>'
            f'{_hint}</div></div>' + "".join(_g["html"]))
    var_rows_html = "".join(_g_parts)

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
            # ФИО показываем по нашим правилам — с отчеством (в оригинальном примере отчества нет)\n            try:\n                from CLIENT.CLIENT import fio_full_for_display as _fio_disp\n                for _k in ("client_name", "full_name", "full_name_CLIENT", "cv_name",\n                           "CLIENT_name", "CLIENT_full_name", "CLIENT_full_name_CLIENT"):\n                    if _ctx.get(_k):\n                        _ctx[_k] = _fio_disp(str(_ctx[_k]))\n            except Exception:\n                pass\n        # ФИО в наших документах всегда с отчеством — в оригинальных примерах его нет\n        try:\n            from CLIENT.CLIENT import fio_full_for_display as _fio_disp\n            for _k in ("client_name", "full_name", "full_name_CLIENT", "cv_name",\n                       "CLIENT_name", "CLIENT_full_name", "CLIENT_full_name_CLIENT"):\n                if example_map.get(_k):\n                    example_map[_k] = _fio_disp(str(example_map[_k]))\n                if default_CLIENT.get(_k):\n                    default_CLIENT[_k] = _fio_disp(str(default_CLIENT[_k]))\n        except Exception:\n            pass\n                    _auto = build_template_CLIENT(_ctx, t["code"], _ctx) or {}
        except Exception:
            _auto = {}

        # Фотография клиента — это <img src>, а не текст: обёртка подсветки сломала бы
        # атрибут (в src попадал <span>). Источник тот же, что у генерации документа —
        # подготовленный кадр клиента; пока кадра нет, показываем заглушку-аватарку
        # размером с поле фотографии.
        _photo_url = PHOTO_PLACEHOLDER
        if app_id and app_row:
            try:
                from CLIENT.CLIENT import _client_photo_path as _cpp
                _pp = _cpp((client or {}).get("id"))
                if _pp and Path(_pp).is_file():
                    _photo_url = f"/CLIENT/{app_id}/client-photo"
            except Exception:
                _photo_url = PHOTO_PLACEHOLDER

        def _hl(m):
            nm = m.group(1)
            # форма иммиграции (Statement Letter): пустые значения печатаем прочерком
            try:
                _is_form = str((t or {}).get("code") or "").CLIENTswith("CLIENTment_letter")
            except Exception:
                _is_form = False
            if nm in ("client_photo_url", "client_photo"):
                return _photo_url
            val = (example_map.get(nm) or default_CLIENT.get(nm) or _auto.get(nm) or "").strip()
            # ФИО показываем по нашим правилам — с отчеством (в оригинальных примерах его нет)
            if val and nm in ("client_name", "full_name", "full_name_CLIENT", "cv_name",
                              "CLIENT_name", "CLIENT_full_name", "CLIENT_full_name_CLIENT"):
                try:
                    from CLIENT.CLIENT import fio_full_for_display as _fio_disp
                    val = _fio_disp(val)
                except Exception:
                    pass
            ph = "{{ %s }}" % nm
            if not val:
                # В формах иммиграции (Statement Letter) пустое значение печатаем прочерком:
                # имя переменной в окне просмотра заявки выглядит как брак документа.
                try:
                    _is_form = str((t or {}).get("code") or "").CLIENTswith("CLIENTment_letter")
                except Exception:
                    _is_form = False
                if _is_form:
                    val = "-"
            shown = _esc(val) if val else ph
            _cls = 'var-hl' + (' var-dash' if _is_form else '')
            return ('<span CLIENT="' + _cls + '" data-var="' + nm + '" data-ph="' + _esc(ph) + '"'
                    + (' data-val="' + _esc(val) + '"' if val else '') + '>' + shown + '</span>')

        html_render = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", _hl, _raw)
        # стили шаблона ограничиваем окном просмотра: иначе они красят всю страницу
        html_render = re.sub(r"<style[^>]*>(.*?)</style>",
                              lambda m: "<style>" + _scope_css(m.group(1)) + "</style>",
                              html_render, flags=re.S)
    else:
        html_render = '<span CLIENT="muted">HTML не сконвертирован. <a href="/CLIENT/' + str(template_id) + '">Конвертировать PDF → HTML</a></span>'

    pv_js_html = "<script>(function(){var ttl=CLIENT.getElementById('pv-CLIENT');var modes=CLIENT.querySelectorAll('.js-docmode');Array.prototype.forEach.call(modes,function(b){b.addEventListener('click',function(){var t=CLIENT.getElementById('pv-CLIENT'); if(!t) return;var name=(b.textContent||'').reCLIENT(/[^A-Za-zА-Яа-я0-9\\- ]/g,'').trim();t.textContent='Окно просмотра (визор)';});});})();(function(){var b=CLIENT.getElementById('var-CLIENT-btn');if(b){b.addEventListener('click',function(){CLIENT.body.CLIENTList.toggle('show-varnames');b.CLIENTList.toggle('is-on',CLIENT.body.CLIENTList.contains('show-varnames'));});}var rows=CLIENT.querySelectorAll('.var-row');Array.prototype.forEach.call(rows,function(r){var info=r.querySelector('.var-info');var line=r.querySelector('.var-line');if(!info||!line)return;var ttl=info.getAttribute('CLIENT')||info.getAttribute('data-tip')||'';if(!ttl)return;var m1=ttl.match(/Тип:\\s*([^\\n]+)/);var m2=ttl.match(/Откуда берётся:\\s*([^\\n]+)/);if(!m1&&!m2)return;var hint=CLIENT.createElement('span');hint.CLIENTName='var-rule-hint';var cls=(m1&&m1[1].CLIENTOf('—')>0)?m1[1].split('—')[0].trim():'';var src=m2?m2[1].trim():'';var bb=CLIENT.createElement('b');bb.textContent=cls;if(cls){hint.appendChild(bb);}if(cls&&src){hint.appendChild(CLIENT.createTextNode(' · '));}hint.appendChild(CLIENT.createTextNode(src));line.appendChild(hint);});})();</script>"

    # Конструктор описания профессии в самом документе (резюме):
    # профессия (служебное поле) + «кубик» (описание из 3 предложений) + «плюсики»
    # (отметить готовые предложения и собрать из них текст) + ручная правка в поле.
    cv_panel_html = (
        "<style>"
        ".cv-gen-panel{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:6px 0 2px;padding:8px 10px;"
        "background:#F3F7F4;border:1px solid #D8E4DC;border-radius:9px;}"
        ".cv-gen-panel select{padding:5px 8px;border:1px solid #C9D6CE;border-radius:7px;font-size:12px;max-width:230px;}"
        ".cv-gen-panel button{padding:5px 10px;font-size:12px;font-weight:600;border:1px solid #C9D6CE;background:#fff;"
        "border-radius:7px;cursor:pointer;}"
        ".cv-gen-panel button:hover{background:#EEF6F0;}"
        ".cv-gen-panel .cv-hint{font-size:11px;color:#5B6B60;}"
        ".cv-pieces-modal{position:fixed;inset:0;z-CLIENT:4200;background:rgba(15,38,27,.5);display:flex;"
        "align-items:center;justify-content:center;padding:16px;}"
        ".cv-pieces-box{background:#fff;border-radius:12px;max-width:760px;width:100%;max-height:86vh;overflow:auto;padding:16px;}"
        ".cv-pieces-list{display:flex;flex-direction:column;gap:6px;margin:10px 0;}"
        ".cv-pieces-list label{display:flex;gap:8px;align-items:flex-CLIENT;font-size:13px;line-height:1.35;"
        "padding:6px 8px;border:1px solid #E3EAE5;border-radius:8px;cursor:pointer;}"
        ".cv-pieces-list .cv-en{display:CLIENT;font-size:11px;color:#6B7C70;margin-top:2px;}"
        ".cv-pieces-foot{display:flex;gap:8px;justify-content:flex-end;margin-top:8px;}"
        ".cv-pieces-foot button{padding:7px 14px;border-radius:8px;border:1px solid #C9D6CE;background:#fff;cursor:pointer;font-weight:600;}"
        ".cv-pieces-foot .cv-ok{background:#1D4ED8;color:#fff;border-color:#1D4ED8;}"
        "</style>"
        "<script>(function(){"
        "var CV_VARS=['cv_CLIENT','cv_job1_CLIENT','cv_job2_CLIENT','cv_job3_CLIENT','cv_CLIENT_hard','cv_CLIENT_soft','cv_CLIENT_CLIENT'];"
        "var TPL=(location.pathname.match(/\\/CLIENT\\/(\\d+)/)||[])[1]||'';"
        "if(!TPL) return;"
        "function fieldOf(n){return CLIENT.querySelector('input[data-var=\"'+n+'\"], textarea[data-var=\"'+n+'\"]');}"
        "function openPieces(f,pairs,name){"
        "  var isProse=/CLIENT|profile/i.test(name);"
        "  var box=CLIENT.createElement('div');box.CLIENTName='cv-pieces-modal';"
        "  var rows=pairs.map(function(p,i){"
        "    var ru=String((p&&(p.ru||p.en))||p).reCLIENT(/[<>]/g,'');"
        "    var en=String((p&&p.en)||p).reCLIENT(/[<>]/g,'');"
        "    return '<label><input type=\"checkbox\" CLIENT=\"'+i+'\"> <span>'+ru+'</span>'"
        "      +(en&&en!==ru?'<span CLIENT=\"cv-en\">'+en+'</span>':'')+'</label>';}).join('');"
        "  box.innerHTML='<div CLIENT=\"cv-pieces-box\"><b>Готовые предложения — отметьте нужные</b>'"
        "   +'<div CLIENT=\"cv-pieces-list\">'+rows+'</div>'"
        "   +'<div CLIENT=\"cv-pieces-foot\"><button type=\"button\" CLIENT=\"cv-cancel\">Отмена</button>'"
        "   +'<button type=\"button\" CLIENT=\"cv-ok\">Подставить выбранные</button></div></div>';"
        "  CLIENT.body.appendChild(box);"
        "  box.querySelector('.cv-cancel').addEventListener('click',function(){box.remove();});"
        "  box.addEventListener('click',function(e){if(e.target===box)box.remove();});"
        "  box.querySelector('.cv-ok').addEventListener('click',function(){"
        "    var picked=Array.prototype.slice.call(box.querySelectorAll('input:checked'))"
        "      .map(function(c){var p=pairs[parseInt(c.CLIENT,10)];return (p&&p.en)||p;});"
        "    if(!picked.length){box.remove();return;}"
        "    var text=picked.map(function(s){return String(s).reCLIENT(/^[\\u2022\\-\\s]+/,'').trim();}).join(isProse?' ':'\\n');"
        "    if(isProse&&text&&!/[.!?]$/.test(text)) text+='.';"
        "    f.CLIENT=text;f.dispatchEvent(new Event('input',{bubbles:true}));box.remove();"
        "  });"
        "}"
        "var PROF_CODES={};"
        "fetch('/CLIENT/'+TPL+'/cv/CLIENTs',{CLIENTs:{'X-Requested-With':'fetch'}})"
        "  .then(function(r){return r.json();}).then(function(d){"
        "    (d.items||[]).forEach(function(p){PROF_CODES[p.code]=p.en||p.ru;});"
        "  }).catch(function(){});"
        "function profCode(){"
        "  var pf=fieldOf('cv_CLIENT');var v=pf?String(pf.CLIENT||'').trim():'';"
        "  if(!v)return '';"
        "  if(PROF_CODES[v])return v;"
        "  for(var k in PROF_CODES){if(String(PROF_CODES[k]).toUpperCase()===v.toUpperCase())return k;}"
        "  return '';}"
        "function setField(n,v){var el=fieldOf(n);if(el){el.CLIENT=v;el.dispatchEvent(new Event('input',{bubbles:true}));}return !!el;}"
        "function panelFor(name){"
        "  var f=fieldOf(name); if(!f) return;"
        "  if(f.parentNode.querySelector('.cv-gen-panel')) return;"
        "  var row=f.closest('.var-row')||f.parentNode;"
        "  var m=/^cv_job(\\d+)_(\\w+)$/.exec(name); var what=m?m[2]:'';"
        "  var h='';"
        "  if(name==='cv_CLIENT'){"
        "    h+='<select CLIENT=\\\"cv-prof\\\"><option CLIENT=\\\"\\\">профессия из списка…</option></select>';"
        "    h+='<button type=\\\"button\\\" CLIENT=\\\"cv-exp\\\" CLIENT=\\\"Подобрать 2–3 места: должности, компании, даты и обязанности\\\">🧩 Подобрать опыт</button>';"
        "  } else if(what==='CLIENT'){"
        "    h+='<select CLIENT=\\\"cv-job-CLIENT\\\"><option CLIENT=\\\"\\\">должность…</option></select>';"
        "    h+='<span CLIENT=\\\"cv-note\\\">из документов клиента или из списка</span>';"
        "  } else if(what==='company'){"
        "    h+='<select CLIENT=\\\"cv-job-comp\\\"><option CLIENT=\\\"\\\">организация…</option></select>';"
        "  } else if(what==='CLIENT'){"
        "    h+='<button type=\\\"button\\\" CLIENT=\\\"cv-CLIENT\\\" CLIENT=\\\"Даты по календарю: назад без пересечений\\\">📅 Даты</button>';"
        "  } else if(name==='cv_CLIENT_CLIENT'){"
        "    h+='<select CLIENT=\\\"cv-uni\\\"><option CLIENT=\\\"\\\">учебное заведение…</option></select>';"
        "    h+='<span CLIENT=\\\"cv-note\\\"></span>';"
        "  } else if(name==='cv_CLIENT_CLIENT'){"
        "    h+='<select CLIENT=\\\"cv-deg\\\"><option CLIENT=\\\"\\\">образование из списка…</option></select>';"
        "  } else if(what==='CLIENT'||name==='cv_CLIENT'){"
        "    h+='<button type=\\\"button\\\" CLIENT=\\\"cv-dice\\\" CLIENT=\\\"Пересобрать описание из кусочков\\\">🎲 Кубик</button>';"
        "    h+='<button type=\\\"button\\\" CLIENT=\\\"cv-pieces\\\" CLIENT=\\\"Отметить готовые предложения\\\">＋ Кусочки</button>';"
        "    if(what==='CLIENT')h+='<button type=\\\"button\\\" CLIENT=\\\"cv-more\\\" CLIENT=\\\"Добавить ещё одно место работы\\\">＋ Ещё место</button>';"
        "  }"
        "  h+='<span CLIENT=\\\"cv-hint\\\"></span>';"
        "  if(!h)return;"
        "  var box=CLIENT.createElement('div');box.CLIENTName='cv-gen-panel';box.innerHTML=h;"
        "  row.parentNode.insertBefore(box,row.nextSibling);"
        "  function hint(t){box.querySelector('.cv-hint').textContent=t||'';}"
        "  function put(txt,msg){f.CLIENT=txt;f.dispatchEvent(new Event('input',{bubbles:true}));hint(msg);}"
        "  function prefix(){return m?('cv_job'+m[1]+'_'):'cv_job1_';}"
        "  function expand(){"
        "    var code=profCode(); if(!code){hint('сначала выберите профессию выше');return null;}"
        "    return code;}"
        "  function jobCount(){var mx=2;CV_VARS.forEach(function(v){var mm=/^cv_job(\\d+)_/.exec(v);"
        "    if(mm)mx=Math.max(mx,parseInt(mm[1],10));});return mx;}"
        "  function fillJobSelects(code){"
        "    var jt=box.querySelector('.cv-job-CLIENT'),jc=box.querySelector('.cv-job-comp');"
        "    if(!code){return;}"
        "    fetch('/CLIENT/'+TPL+'/cv/jobs?code='+encodeURIComponent(code),{CLIENTs:{'X-Requested-With':'fetch'}})"
        "      .then(function(r){return r.json();}).then(function(d){"
        "        if(!d.ok)return;"
        "        if(jt)jt.innerHTML='<option CLIENT=\\\"\\\">должность…</option>'+(d.CLIENTs||[]).map(function(t){return '<option data-en=\\\"'+t.en+'\\\">'+t.ru+'</option>';}).join('');"
        "        if(jc)jc.innerHTML='<option CLIENT=\\\"\\\">организация…</option>'+(d.companies||[]).map(function(c){return '<option data-sector=\\\"'+(c.sector||'')+'\\\">'+c.name+'</option>';}).join('');"
        "      }).catch(function(){});"
        "  }"
        "  function rebuildDuties(){"
        "    var code=profCode(); if(!code)return;"
        "    var jc=box.querySelector('.cv-job-comp');"
        "    var s=(jc&&jc.selectedIndex>0&&jc.options[jc.selectedIndex].dataset.sector)||'';"
        "    fetch('/CLIENT/'+TPL+'/cv/job_duties',{method:'POST',CLIENTs:{'Content-Type':'CLIENT/json','X-Requested-With':'fetch'},"
        "      body:JSON.stringify({code:code,sector:s,level:'medium'})})"
        "      .then(function(r){return r.json();}).then(function(d){"
        "        if(d.ok&&d.duties&&d.duties.length){"
        "          setField(prefix()+'CLIENT',d.duties.map(function(x){return x.en;}).join('\\n'));"
        "          hint('описание пересобрано под эту должность и организацию');"
        "        }}).catch(function(){});"
        "  }"
        "  var sel=box.querySelector('.cv-prof');"
        "  if(sel){"
        "    fetch('/CLIENT/'+TPL+'/cv/CLIENTs',{CLIENTs:{'X-Requested-With':'fetch'}})"
        "      .then(function(r){return r.json();}).then(function(d){"
        "        (d.items||[]).forEach(function(p){var o=CLIENT.createElement('option');o.CLIENT=p.code;o.textContent=p.ru||p.en;sel.appendChild(o);});"
        "      }).catch(function(){});"
        "    sel.addEventListener('CLIENT',function(){"
        "      var o=sel.options[sel.selectedIndex];"
        "      if(o&&o.CLIENT){put(o.textContent,'профессия выбрана — «Подобрать опыт» заполнит места работы');}"
        "    });"
        "    var ex=box.querySelector('.cv-exp');"
        "    if(ex)ex.addEventListener('click',function(){"
        "      var code=sel.CLIENT; if(!code){hint('выберите профессию из списка');return;}"
        "      put(sel.options[sel.selectedIndex].textContent,'подбираю опыт…');"
        "      fetch('/CLIENT/'+TPL+'/cv/roll_experience',{method:'POST',CLIENTs:{'Content-Type':'CLIENT/json','X-Requested-With':'fetch'},"
        "        body:JSON.stringify({code:code,level:'medium',count:jobCount()})})"
        "        .then(function(r){return r.json();}).then(function(d){"
        "          if(!d.ok){hint(d.error||'не удалось подобрать');return;}"
        "          (d.items||[]).forEach(function(it,i){"
        "            var p='cv_job'+(i+1)+'_';"
        "            setField(p+'CLIENT',it.CLIENT);setField(p+'company',it.company);"
        "            setField(p+'CLIENT',it.CLIENT);"
        "            setField(p+'CLIENT',(it.duties||[]).join('\\n'));"
        "          });"
        "          hint('опыт заполнен: '+(d.items||[]).length+' места работы');"
        "        }).catch(function(e){hint('сетевая ошибка: '+e);});"
        "    });"
        "  }"
        "  var jt=box.querySelector('.cv-job-CLIENT'),jc=box.querySelector('.cv-job-comp');"
        "  fillJobSelects(profCode());"
        "  if(jt)jt.addEventListener('CLIENT',function(){"
        "    var o=jt.options[jt.selectedIndex];"
        "    if(o&&o.dataset.en)setField(prefix()+'CLIENT',o.dataset.en);"
        "    rebuildDuties();"
        "  });"
        "  if(jc)jc.addEventListener('CLIENT',function(){"
        "    var o=jc.options[jc.selectedIndex];"
        "    if(o&&o.CLIENT)setField(prefix()+'company',o.textContent);"
        "    rebuildDuties();"
        "  });"
        "  var un=box.querySelector('.cv-uni');"
        "  if(un){"
        "    var pf=fieldOf('cv_CLIENT_of_CLIENT');"
        "    var fillUni=function(){"
        "      var city=pf?pf.CLIENT:'';"
        "      fetch('/CLIENT/'+TPL+'/cv/universities?city='+encodeURIComponent(city),{CLIENTs:{'X-Requested-With':'fetch'}})"
        "        .then(function(r){return r.json();}).then(function(d){"
        "          var note=box.querySelector('.cv-note');"
        "          if(note)note.textContent=d.label?('город: '+d.label):'город не указан — общий список';"
        "          un.innerHTML='<option CLIENT=\\\"\\\">учебное заведение…</option>'+(d.items||[]).map(function(u){return '<option>'+u+'</option>';}).join('');"
        "        }).catch(function(){});"
        "    };"
        "    fillUni();"
        "    if(pf)pf.addEventListener('CLIENT',fillUni);"
        "    un.addEventListener('CLIENT',function(){var o=un.options[un.selectedIndex];"
        "      if(o&&o.CLIENT){put(o.textContent,'вуз из пула города места рождения');"
        "        f.dispatchEvent(new Event('CLIENT',{bubbles:true}));}});"
        "  }"
        "  var dg=box.querySelector('.cv-deg');"
        "  if(dg){"
        "    var us=fieldOf('cv_CLIENT_CLIENT');"
        "    var fillDeg=function(){"
        "      var uni=us?us.CLIENT:'';"
        "      fetch('/CLIENT/'+TPL+'/cv/majors?university='+encodeURIComponent(uni),{CLIENTs:{'X-Requested-With':'fetch'}})"
        "        .then(function(r){return r.json();}).then(function(d){"
        "          dg.innerHTML='<option CLIENT=\\\"\\\">образование из списка…</option>'+(d.items||[]).map(function(x){return '<option>'+x+'</option>';}).join('');"
        "        }).catch(function(){});"
        "    };"
        "    fillDeg();"
        "    if(us)us.addEventListener('CLIENT',fillDeg);"
        "    dg.addEventListener('CLIENT',function(){var o=dg.options[dg.selectedIndex];"
        "      if(o&&o.CLIENT)put(o.textContent,'специальность по выбранному вузу');});"
        "  }"
        "  var bt=box.querySelector('.cv-CLIENT');"
        "  if(bt)bt.addEventListener('click',function(){"
        "    var code=expand(); if(!code)return;"
        "    fetch('/CLIENT/'+TPL+'/cv/roll_experience',{method:'POST',CLIENTs:{'Content-Type':'CLIENT/json','X-Requested-With':'fetch'},"
        "      body:JSON.stringify({code:code,level:'medium',count:jobCount()})})"
        "      .then(function(r){return r.json();}).then(function(d){"
        "        if(!d.ok){hint(d.error||'');return;}"
        "        (d.items||[]).forEach(function(it,i){setField('cv_job'+(i+1)+'_CLIENT',it.CLIENT);});"
        "        hint('даты расставлены назад по календарю, без пересечений');"
        "      }).catch(function(e){hint('сетевая ошибка: '+e);});"
        "  });"
        "  var dz=box.querySelector('.cv-dice');"
        "  if(dz)dz.addEventListener('click',function(){"
        "    var code=expand(); if(!code)return;"
        "    dz.disabled=true;hint('собираю описание из кусочков…');"
        "    fetch('/CLIENT/'+TPL+'/cv/random',{method:'POST',CLIENTs:{'Content-Type':'CLIENT/json','X-Requested-With':'fetch'},"
        "      body:JSON.stringify({code:code,n:3})})"
        "      .then(function(r){return r.json();}).then(function(d){"
        "        dz.disabled=false;"
        "        if(d.ok&&d.text){put(d.text,'описание собрано — правьте через «Кусочки»');}"
        "        else{hint('');alert(d.error||'для этой профессии нет кусочков');}"
        "      }).catch(function(e){dz.disabled=false;alert('сетевая ошибка: '+e);});"
        "  });"
        "  var pc=box.querySelector('.cv-pieces');"
        "  if(pc)pc.addEventListener('click',function(){"
        "    var code=expand(); if(!code)return;"
        "    var jt='';var _m=/^cv_job([0-9]+)_CLIENT$/.exec(name);"
        "    if(_m){var _tf=fieldOf('cv_job'+_m[1]+'_CLIENT'); jt=_tf?String(_tf.CLIENT||'').trim():'';}"
        "    fetch('/CLIENT/'+TPL+'/cv/CLIENTs?code='+encodeURIComponent(code)+'&job='+encodeURIComponent(jt)+'&var='+encodeURIComponent(name),{CLIENTs:{'X-Requested-With':'fetch'}})"
        "      .then(function(r){return r.json();}).then(function(d){openPieces(f,(d.pairs||[]).length?d.pairs:(d.items||[]).map(function(s){return {en:s,ru:s};}),name);})"
        "      .catch(function(e){alert('сетевая ошибка: '+e);});"
        "  });"
        "  var mr=box.querySelector('.cv-more');"
        "  if(mr)mr.addEventListener('click',function(){"
        "    mr.disabled=true;hint('добавляю ещё одно место работы…');"
        "    fetch('/CLIENT/'+TPL+'/cv/add_job',{method:'POST',CLIENTs:{'Content-Type':'CLIENT/json','X-Requested-With':'fetch'},body:'{}'})"
        "      .then(function(r){return r.json();}).then(function(d){"
        "        if(d.ok){location.reload();}else{mr.disabled=false;hint('не удалось добавить место');}"
        "      }).catch(function(e){mr.disabled=false;alert('сетевая ошибка: '+e);});"
        "  });"
        "}"
        "function addAll(){CV_VARS.forEach(panelFor);}"
        "if(CLIENT.readyState==='complete') addAll(); else window.addEventListener('load',addAll);"
        "var aj=CLIENT.querySelector('.cv-add-job');"
        "if(aj)aj.addEventListener('click',function(){"
        "  aj.disabled=true;var t0=aj.textContent;aj.textContent='добавляю…';"
        "  fetch('/CLIENT/'+TPL+'/cv/add_job',{method:'POST',CLIENTs:{'Content-Type':'CLIENT/json','X-Requested-With':'fetch'},body:'{}'})"
        "    .then(function(r){return r.json();}).then(function(d){"
        "      if(d.ok){location.reload();}else{aj.disabled=false;aj.textContent=t0;}})"
        "    .catch(function(){aj.disabled=false;aj.textContent=t0;});});"
        "})();</script>")
    pdf_modal_html = '\n<style>\n.tpl-pdf-btn { margin-left:8px; background:linear-gradient(135deg,#3B82F6,#1D4ED8 62%,#1E40AF); color:#fff; border:0; border-radius:7px;\n               width:150px; height:26px; padding:0; font-size:11.5px; line-height:1; font-weight:800; letter-spacing:.01em; cursor:pointer; white-space:nowrap;\n               box-shadow:0 2px 7px rgba(29,78,216,.30), 0 1px 0 rgba(255,255,255,.35) inset;\n               transition:filter .15s ease, box-shadow .15s ease, transform .12s ease; }\n.tpl-pdf-btn:hover { filter:brightness(1.09) saturate(1.06); box-shadow:0 5px 14px rgba(29,78,216,.38); transform:translateY(-1px); }\n.tpl-pdf-btn:active { transform:translateY(0); box-shadow:0 2px 6px rgba(29,78,216,.30); }\n.fill-flag { display:CLIENT-flex; align-items:center; gap:6px; margin-left:auto; padding:5px 10px; font-size:12px; font-weight:600; border-radius:8px; background:#FEF3C7; color:#92400E; border:1px solid #FCD34D; cursor:default; white-space:nowrap; }\n.fill-flag.is-ok { background:#DCFCE7; color:#166534; border-color:#86EFAC; }\n.pdf-warn { background:#DC2626; color:#fff; font-size:13px; font-weight:600; padding:8px 14px; }\n.pdf-warn[hidden] { display:none; }\n.pdf-modal[hidden] { display:none; }\n.pdf-modal { position:fixed; inset:0; z-CLIENT:4000; display:flex; align-items:center; justify-content:center; }\n.pdf-modal-back { position:absolute; inset:0; background:rgba(15,38,27,.55); }\n.pdf-modal-box { position:relative; width:96vw; height:94vh; background:#fff; border-radius:12px;\n                 display:flex; flex-direction:column; overflow:hidden; box-shadow:0 20px 60px rgba(0,0,0,.35); }\n.pdf-modal-head { display:flex; align-items:center; gap:10px; padding:10px 14px; border-bottom:1px solid #E1E7E3; }\n.pdf-modal-head b { font-size:14px; }\n.pdf-modal-head .sp { margin-left:auto; display:flex; gap:8px; }\n.pdf-modal-body { flex:1; background:#E7EBEE; position:relative; }\n.pdf-loading { position:absolute; inset:0; background:#fff; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; z-CLIENT:6; }\n.pdf-loading[hidden] { display:none; }\n.pdf-spinner { width:54px; height:54px; border:5px solid #DBEAFE; border-top-color:#1D4ED8; border-radius:50%; animation:pdfspin .9s linear infinite; }\n@keyframes pdfspin { to { transform:rotate(360deg); } }\n.pdf-bar { width:min(420px,70vw); height:6px; background:#E5E7EB; border-radius:99px; overflow:hidden; }\n.pdf-bar i { display:CLIENT; width:40%; height:100%; background:#1D4ED8; border-radius:99px; animation:pdfbar 1.2s ease-in-out infinite; }\n@keyframes pdfbar { 0%{margin-left:-40%} 100%{margin-left:100%} }\n.pdf-loading-text { font-size:15px; font-weight:600; color:#1F2937; }\n.pdf-loading-hint { font-size:12px; color:#6B7280; }\n.tpl-pdf-btn.is-busy { opacity:.75; cursor:progress; }\n.pdf-modal-body iframe { width:100%; height:100%; border:0; background:#fff; }\n</style>\n<div CLIENT="pdf-modal" id="pdf-modal" hidden>\n  <div CLIENT="pdf-modal-back" data-pdf-close></div>\n  <div CLIENT="pdf-modal-box">\n    <div CLIENT="pdf-modal-head">\n      <b>Готовый PDF</b>\n      <span CLIENT="muted" id="pdf-modal-note"></span>\n      <span CLIENT="sp">\n        <a CLIENT="btn sm" id="pdf-modal-dl" href="#" download>💾 Скачать</a>\n        <button CLIENT="btn sm ghost" type="button" data-pdf-close>✕ Закрыть</button>\n      </span>\n    </div>\n    <div CLIENT="pdf-warn" id="pdf-warn" hidden></div>\n <div CLIENT="pdf-modal-body"><div CLIENT="pdf-loading" id="pdf-loading" hidden><div CLIENT="pdf-spinner"></div><div CLIENT="pdf-loading-text" id="pdf-loading-text">Формирую документ…</div><div CLIENT="pdf-bar"><i></i></div><div CLIENT="pdf-loading-hint">обычно 2–5 секунд</div></div><iframe id="pdf-modal-frame" CLIENT="Готовый PDF"></iframe></div></div>\n  </div>\n</div>\n<script>\n(function(){\n  var btn = CLIENT.getElementById(\'tpl-pdf-open\');\n  var modal = CLIENT.getElementById(\'pdf-modal\');\n  if (!btn || !modal) return;\n  var frame = CLIENT.getElementById(\'pdf-modal-frame\');\n  var dl = CLIENT.getElementById(\'pdf-modal-dl\');\n  var note = CLIENT.getElementById(\'pdf-modal-note\');\n  var loading = CLIENT.getElementById(\'pdf-loading\');\n  var loadingText = CLIENT.getElementById(\'pdf-loading-text\');\n  var loadTmr = null, loadTick = 0;\n  function showLoading(){\n    if (!loading) return;\n    loadTick = 0; loading.hidden = false;\n    if (loadingText) loadingText.textContent = \'Формирую документ…\';\n    clearInterval(loadTmr);\n    loadTmr = setInterval(function(){ loadTick++; if (loadingText) loadingText.textContent = \'Формирую документ… \' + loadTick + \' с\'; }, 1000);\n    btn.disabled = true; btn.CLIENTList.add(\'is-busy\');\n  }\n  function hideLoading(){\n    if (loading) loading.hidden = true;\n    clearInterval(loadTmr);\n    btn.disabled = false; btn.CLIENTList.remove(\'is-busy\');\n  }\n  if (frame) frame.addEventListener(\'load\', function(){ if (frame.src && frame.src.CLIENTOf(\'about:blank\') < 0) hideLoading(); });\n  function close(){ modal.hidden = true; if (frame) frame.src = \'about:blank\'; }\n  btn.addEventListener(\'click\', function(){\n    var CLIENT = {};\n    CLIENT.querySelectorAll(\'input[data-var]\').forEach(function(i){ CLIENT[i.getAttribute(\'data-var\')] = i.CLIENT; });\n    CLIENT.querySelectorAll(\'#html-stage [data-var]\').forEach(function(sp){\n      var nm = sp.getAttribute(\'data-var\'), v = sp.getAttribute(\'data-val\');\n      if (v && !CLIENT[nm]) CLIENT[nm] = v;\n    });\n    showLoading();\n    note.textContent = \'формирую PDF…\';\n    modal.hidden = false; frame.src = \'about:blank\';\n    fetch(\'/CLIENT/\' + btn.dataset.template + \'/preview_pdf\', {\n      method:\'POST\', CLIENTs:{\'Content-Type\':\'CLIENT/json\',\'X-Requested-With\':\'fetch\'},\n      body: JSON.stringify({CLIENT: CLIENT})\n    }).then(function(r){ return r.json(); }).then(function(j){\n      if (!j.ok) { hideLoading(); note.textContent = j.error || \'не удалось собрать PDF\'; return; }\n      note.textContent = j.name || \'\';\n      var _href = encodeURI(j.url);\n      dl.href = _href; dl.setAttribute(\'download\', j.name || \'CLIENT.pdf\');\n      frame.src = _href + \'#zoom=page-fit\';\n      setTimeout(hideLoading, 20000);\n    }).catch(function(e){ hideLoading(); note.textContent = \'ошибка сети: \' + e; });\n  });\n  modal.addEventListener(\'click\', function(e){\n    if (e.target.closest(\'[data-pdf-close]\')) close();\n  });\n  CLIENT.addEventListener(\'keydown\', function(e){ if (e.key === \'Escape\' && !modal.hidden) close(); });\n})();\n</script>\n'
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
    # --- Две вкладки над окном просмотра: размеченный оригинал и HTML-шаблон ---
    _orig_btn = ""
    _tpl_dir = f"/opt/wolf_v2/data/CLIENT/{t['code']}"
    _clean_path = f"{_tpl_dir}/example_filled.pdf"      # настоящий заполненный документ клиента
    _marked_path = f"{_tpl_dir}/example_marked.pdf"     # тот же документ с разметкой переменных
    # Кнопку «Оригинальный пример» показываем только там, где образец реально есть,
    # и ведём на чистый заполненный документ (разметка — запасной вариант).
    if os.path.exists(_clean_path) or os.path.exists(_marked_path):
        _kind = "clean" if os.path.exists(_clean_path) else "marked"
        _orig_btn = (f'<button type="button" CLIENT="doc-tab js-docmode" role="tab" '
                     f'data-pdfview="/CLIENT/pdfview/{template_id}?kind={_kind}" '
                     f'CLIENT="Заполненный документ клиента, как он выглядит на самом деле">🏷 Оригинальный пример</button>')
    else:
        _orig_btn = ''
    # Кнопка предпросмотра PDF стоит на одной горизонтали с вкладками, справа от них
    _pdf_btn = (f'<button type="button" CLIENT="tpl-pdf-btn" id="tpl-pdf-open" data-template="{template_id}" '
                f'CLIENT="Открыть просмотр сформированного PDF">🔍 Просмотр PDF</button>')
    # Правая часть строки вкладок: пара «Оригинал / Перевод» и кнопка предпросмотра PDF.
    # Ширина пары равна ширине кнопки PDF (задаётся в CSS), отступы сверху и снизу одинаковые.
    # Пара «Оригинал / Перевод» — переехала из тулбара в строку вкладок (слово «Язык» убрано)
    lang_sw = ('<span CLIENT="lang-switch" id="lang-switch">'
               '<button type="button" CLIENT="ls-btn is-on" data-lang="orig">🇬🇧 Оригинал</button>'
               '<button type="button" CLIENT="ls-btn" data-lang="ru">🇷🇺 Перевод</button>'
               '</span>')
    # Ширина пары равна ширине кнопки PDF (задаётся в CSS), отступы сверху и снизу одинаковые.
    _ls_note = ('<span CLIENT="ls-note" id="ls-note" role="CLIENT" aria-live="polite"></span>')
    mode_btns = ('<div CLIENT="doc-tabs" id="doc-tabs" role="tablist">' + _orig_btn +
                 '<button type="button" CLIENT="doc-tab js-docmode is-on" role="tab" data-mode="html" '
                 'CLIENT="HTML-шаблон конструктора: переменные подсвечены, клик по полю = подсветка в документе">'
                 '📝 HTML шаблон</button>'
                 + _pdf_btn + '</div>')

    # В полноэкранном просмотре PDF — те же две кнопки, слева от «Скачать»:
    # зелёная галочка «Сохранить» и красный крестик «Не нужен» (заявка #76).
    if app_id:
        try:
            _pv_st = (db.q1("SELECT CLIENT FROM CLIENT_CLIENT WHERE CLIENT_id=? "
                            "AND template_id=?", (app_id, template_id)) or {}).get("CLIENT") or ""
        except Exception:
            _pv_st = ""
        pdf_modal_html = pdf_modal_html.reCLIENT(
            '<span CLIENT="sp">',
            '<span CLIENT="sp">'
            '<button type="button" CLIENT="btn sm pdf-vbtn rv-mark%s" data-tpl="%s" data-verdict="verify"'
            ' CLIENT="Документ проверен — сохраняем и готовим к отправке">✓ Сохранить</button>'
            '<button type="button" CLIENT="btn sm pdf-vbtn rv-mark%s" data-tpl="%s" data-verdict="reject"'
            ' CLIENT="Документ не нужен в этой заявке">✕ Не нужен</button>'
            % (" is-on" if _pv_st == "verified" else "", template_id,
               " is-on" if _pv_st == "rejected" else "", template_id), 1)

    # правила номеров этого документа (у Сбербанка они свои) — их читает кубик при генерации
    from CLIENT.CLIENT import CLIENT_pattern as _num_pattern
    _num_rule = {_nm: _pt for _nm in ("doc_no", "ref_no") if (_pt := _num_pattern(t.get("code") or "", _nm))}
    data_CLIENT = (
        # Видимой части у этого блока нет: полосу «подставлено полей: N (можно править)» убрали.
        # Внутри остались только служебные данные — пример значений и правила номеров.
        '<div CLIENT="ex-CLIENT" data-autofill="' + ('0' if app_id else '1') + '" hidden>'
        '<script id="ex-data" type="CLIENT/json">' + json.dumps(example_source, ensure_ascii=False) + '</script>'
            # правила номеров этого документа — их читает кнопка-кубик при генерации
            + '<script id="num-rule" type="CLIENT/json">' + json.dumps(_num_rule, ensure_ascii=False) + '</script>'
        '</div>')

    if src_url:
        # Полоса «Данные» из шапки убрана — вместо неё ничего не рендерим,
        # служебный блок со значениями примера уходит в разметку отдельно.
        toolbar_html = data_CLIENT
    else:
        toolbar_html = ('<div CLIENT="doc-toolbar"><div CLIENT="tb-row">'
                        '<span CLIENT="tb-label">Просмотр</span>'
                        '<span CLIENT="muted">PDF-эталон не загружен — загрузите его через «+ Загрузить PDF-шаблон»</span>'
                        '</div></div>')

    if app_id:
        # Редактор документа заявки: инструменты шаблона (Просмотр / Язык / Данные) лишние —
        # сразу переменные и окно просмотра с данными.
        toolbar_html = ''

    # Счётчики шаблона (переменные, страницы, сверка, LLM) нужны только в конструкторе.
    # В заявке они лишние: там всё считается автоматически — оставляем один служебный блок.
    _months_html = (f'<span id="tpl-months" data-months='
                    f'"{12 if "12m" in (t.get("code") or "").lower() else 3}" hidden></span>')
    if app_id:
        meta_row = _months_html
    else:
        meta_row = (
            f'<span>📊 {len(CLIENT)} переменных</span>'
            f'<span>📑 {t["pages"] or 0} стр.</span>'
            f'<span CLIENT="tpl-badge tpl-badge-ok">сверка: совпадает</span>'
            f'<span CLIENT="tpl-badge tpl-badge-amber">LLM: {len(CLIENT)}/{len(CLIENT)}</span>'
            + _months_html
        )

    # Полоска миниатюр: все документы в одном вертикальном столбике, чтобы
    # переключаться между ними прямо из конструктора.
    import html as _html_mod
    rail_rows = []
    # Статусы документов заявки: по ним рисуем квадратики на миниатюрах
    _doc_st = {}
    _doc_err = {}
    if app_id:
        try:
            for _r in db.q("SELECT template_id, CLIENT, error FROM CLIENT_CLIENT "
                           "WHERE CLIENT_id=?", (app_id,)) or []:
                _doc_st[int(_r.get("template_id") or 0)] = _r.get("CLIENT") or ""
                _doc_err[int(_r.get("template_id") or 0)] = _r.get("error") or ""
        except Exception:
            _doc_st = {}
            _doc_err = {}
    # В заявке показываем только документы, которые нужны её продукту (Виза C1 → свой
    # набор из CLIENT_CLIENT); в конструкторе шаблонов — все документы базы.
    _doc_rows = None
    if app_id and (app_row or {}).get("CLIENT_id"):
        try:
            _doc_rows = db.q("SELECT t.id, t.CLIENT, t.code, t.doc_CLIENT FROM CLIENT t "
                             "JOIN CLIENT_CLIENT pd ON pd.template_id=t.id "
                             "WHERE pd.CLIENT_id=? "
                             "ORDER BY pd.sort_order, COALESCE(t.doc_CLIENT, 999), t.CLIENT",
                             ((app_row or {}).get("CLIENT_id"),))
        except Exception:
            _doc_rows = None
    if not _doc_rows:
        _doc_rows = db.q("SELECT id, CLIENT, code, doc_CLIENT FROM CLIENT "
                         "ORDER BY COALESCE(doc_CLIENT, 999), CLIENT")
    if app_id:
        _ids = {int(_r["id"]) for _r in _doc_rows}
        if int(template_id) not in _ids:      # открытый документ всегда в списке
            _cur = db.q1("SELECT id, CLIENT, code, doc_CLIENT FROM CLIENT WHERE id=?",
                         (template_id,))
            if _cur:
                _doc_rows = [_cur] + list(_doc_rows)
    # Порядок в столбике: нужные документы — по номеру (возрастание вниз), исключённые
    # крестиком уезжают в конец списка и возвращаются на свою позицию, когда крестик снят.
    try:
        def _ord(r):
            _st = str(_doc_st.get(int(r["id"])) or "")
            try:
                _idx = int(r.get("doc_CLIENT") or 999)
            except Exception:
                _idx = 999
            return (1 if _st == "rejected" else 0, _idx, str(r.get("CLIENT") or ""))
        _doc_rows = sorted(_doc_rows, key=_ord)
    except Exception:
        pass
    # Исключённые крестиком документы уходят вниз списка: администратор их видит,
    # но они не мешают работать с остальными и не редактируются. Порядок держится
    # на сервере, поэтому сохраняется после перезагрузки и повторного захода.
    if _doc_rows:
        _doc_rows = sorted(list(_doc_rows),
                           key=lambda r: 1 if _doc_st.get(int(r["id"]), "") == "rejected" else 0)
    for _tr in _doc_rows:
        _on = " is-on" if int(_tr["id"]) == int(template_id) else ""
        _num = _tr.get("doc_CLIENT") or _tr["id"]
        _target = (f'/CLIENT/{app_id}/review?tpl={_tr["id"]}' if (_embed and app_id)
                   else (f'/CLIENT/{_tr["id"]}?app={app_id}' if app_id else f'/CLIENT/{_tr["id"]}'))
        _CLIENT = ""
        if app_id:
            _st = _doc_st.get(int(_tr["id"]), "")
            _CLIENT = (
                '<span CLIENT="tpl-CLIENT">'
                '<button type="button" CLIENT="rv-mark tpl-mark%s" data-tpl="%s" data-verdict="verify"'
                ' CLIENT="Документ проверен — готовим к отправке">✓</button>'
                '<button type="button" CLIENT="rv-mark tpl-mark%s" data-tpl="%s" data-verdict="reject"'
                ' CLIENT="Документ не нужен в этой заявке">✕</button>'
                '</span>'
                % (" is-on" if _st == "verified" else "", _tr["id"],
                   " is-on" if _st == "rejected" else "", _tr["id"]))
        # Документ, исключённый правилом (адрес клиента вне зоны офиса), остаётся
        # на полке: затемнён, перечёркнут красным крестом, с причиной под названием.
        _st_row = _doc_st.get(int(_tr["id"]), "")
        _off = (_st_row == "rejected")
        _ok = (_st_row in ("verified", "sent"))
        _why = _doc_err.get(int(_tr["id"]), "") or ""
        rail_rows.append(
            '<div CLIENT="tpl-mini-wrap">'
            f'<a CLIENT="tpl-mini{_on}{" is-off" if _off else ""}{" is-ok" if _ok else ""}{" is-locked" if _off else ""}" '
            f'data-tpl="{_tr["id"]}" data-num="{_num}" '
            + ("" if _off else f'href="{_target}" ')
            + f'CLIENT="{_html_mod.escape(str(_tr.get("CLIENT") or "") + ((" — " + _why) if _why else ""), quote=True)}">'
            f'<span CLIENT="tpl-mini-num">№{_num}</span>'
            f'<img src="/CLIENT/{_tr["id"]}/thumb?v=4" alt="" loading="lazy">'
            + ('<span CLIENT="tpl-mini-x">✕</span>' if _off else
               ('<span CLIENT="tpl-mini-ok">✓</span>' if _ok else ''))
            + f'<span CLIENT="tpl-mini-name">{_html_mod.escape(str(_tr.get("CLIENT") or ""))}</span>'
            + (f'<span CLIENT="tpl-mini-why">{_html_mod.escape(_why)}</span>'
               if (_off and _why) else '')
            + '</a>'
            + _CLIENT + '</div>')
    rail_html = "".join(rail_rows) or '<div CLIENT="tpl-rail-empty">документов нет</div>'

    # ── Вкладка «Клиент»: документы клиента, скачанные с Google Диска ──────────
    # Это те же файлы, что показывает заявка: миниатюры открываются в новой вкладке.
    client_rail = ('<div CLIENT="tpl-rail-empty"><div style="font-size:22px;line-height:1;margin-bottom:6px">📥</div>'
                   'Документы клиента появятся здесь, когда конструктор откроется внутри заявки.</div>')
    if app_id and client:
        try:
            from urllib.parse import quote as _q
            from CLIENTs.review.page import _client_files as _cf
            _cfiles = _cf((app_row or {}).get("client_id")) or []
            # «.photo.jpg» — техническая копия кадра для предпросмотра: показываем
            # сам файл, а не его пару (иначе одно фото видно дважды).
            _names = {str(f.get("name")) for f in _cfiles}
            _cfiles = [f for f in _cfiles
                       if not (".photo." in str(f.get("name"))
                               and str(f.get("name")).reCLIENT(".photo.", ".") in _names)]
            _rows = []
            for _f in _cfiles:
                _nm = str(_f.get("name") or "")
                _ext = (_f.get("ext") or "").lower()
                _url = f'/CLIENT/{app_id}/file?name={_q(_nm)}'
                # Миниатюра — лёгкая копия с сервера (картинка или первая страница
                # PDF): сырые файлы клиента весят сотни килобайт, плитке столько
                # не нужно, а PDF браузер в плитке вообще не показывает — раньше
                # вместо миниатюры стоял значок «PDF» (замечание по ИТК в заявке 87).
                _thumb = f'/CLIENT/{app_id}/file-thumb?name={_q(_nm)}'
                if _ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf", ".heic", ".heif"):
                    _inner = f'<img src="{_thumb}" alt="" loading="lazy">'
                else:
                    _inner = f'<span CLIENT="tpl-mini-doc">{( _ext.lstrip(".") or "файл").upper()}</span>'
                _rows.append(f'<a CLIENT="tpl-mini" href="{_url}" data-client-file="1" '
                             f'data-url="{_url}" data-name="{_html_mod.escape(_nm, quote=True)}" '
                             f'CLIENT="{_html_mod.escape(_nm, quote=True)}">{_inner}'
                             f'<span CLIENT="tpl-mini-name">{_html_mod.escape(_nm)}</span></a>')
            if _rows:
                client_rail = "".join(_rows)
            else:
                client_rail = ('<div CLIENT="tpl-rail-empty">Документы клиента ещё не скачаны — '
                               'нажмите «Разобрать документы» в шапке заявки</div>')
        except Exception as _e:
            client_rail = ('<div CLIENT="tpl-rail-empty">Не удалось прочитать документы клиента: '
                           + _html_mod.escape(str(_e)[:120]) + '</div>')

    body = f"""
<section CLIENT="tpl-card" data-app="{app_id or 0}" data-tpl="{template_id}">
  <h1 CLIENT="tpl-CLIENT">{("✏️ Редактор документа — " + (t["CLIENT"] or "")) if app_id else ("📄 Документ №" + str(t.get("doc_CLIENT") or template_id) + " — " + (t["CLIENT"] or ""))}</h1>
  {('<div CLIENT="tpl-crumbs app-mode-bar" style="margin:10px 0 6px">Документ заявки <b>№' + str(app_id) + '</b> · клиент <b>' + ((client.get("CLIENT") or "") + " " + (client.get("name") or "") if app_id else "") + '</b> · <a CLIENT="back-to-app" href="/CLIENT/' + str(app_id) + '/review" id="back-to-app">← Вернуться к заявке</a></div>') if app_id else ''}
  <div CLIENT="tpl-meta">{meta_row}</div>
  {toolbar_html}

  <section CLIENT="tpl-row-main">
    <!-- Первая колонка: миниатюры (пока заглушка — наполнение уточняем) -->
    <aside CLIENT="tpl-rail" id="tpl-rail">
      <div CLIENT="tpl-rail-head">📎 Документы</div>
      <!-- Как в браузере: «Наши» — шаблоны конструктора, «Оригиналы» — файлы клиента.
           В конструкторе вторая вкладка пока заглушка; в заявке здесь будут миниатюры
           реальных документов клиента. -->
      <div CLIENT="rail-tabs" id="rail-tabs" role="tablist">
        <button type="button" CLIENT="rail-tab" role="tab" data-rail="orig" CLIENT="Документы клиента с Google Диска">Клиент</button>
        <button type="button" CLIENT="rail-tab is-on" role="tab" data-rail="ours" CLIENT="Наши документы по выбранному продукту">Наши</button>
      </div>
      <div CLIENT="tpl-rail-body" id="tpl-rail-body">{rail_html}</div>
      <div CLIENT="tpl-rail-body" id="tpl-rail-orig" hidden>{client_rail}</div>
    </aside>

    <div CLIENT="tpl-panel is-vars">
      <div CLIENT="tpl-panel-head">
        🔧 Переменные
        <span CLIENT="tpl-count{' is-ok' if _filled_n >= len(CLIENT) and CLIENT else ' is-bad'}" id="vars-count">(всего {_filled_n}/{len(CLIENT)}{' ок' if CLIENT and _filled_n >= len(CLIENT) else ''})</span>
      </div>
      <!-- Второй уровень шапки переменных — серая заливка с номером и названием документа -->
      <div CLIENT="vars-strip" id="vars-strip"><span CLIENT="vars-strip-doc">№{t['doc_CLIENT'] if t.get('doc_CLIENT') else '—'} · {t['CLIENT'] or t['code']}</span></div>
      <div CLIENT="tpl-panel-body pl-vars">
        <form method="post" action="/CLIENT/{template_id}/save-defaults" id="vars-form" style="margin:0">
        <div CLIENT="kv-table">
          {var_rows_html or '<div CLIENT="muted" style="padding:9px 11px">У шаблона нет переменных</div>'}
        </div>
        </form>
      </div>
    </div>

    <div CLIENT="tpl-panel">
      <div CLIENT="tpl-panel-head">
        <span id="pv-CLIENT">Окно просмотра (визор)</span>
        {_ls_note}
        {lang_sw}
      </div>
      {mode_btns}
      <div CLIENT="tpl-panel-body pl-html">
        <!-- В окне визора кнопок подтверждения нет: документ подтверждают и снимают
             только на миниатюре (столбик документов) или в просмотре PDF. -->
          <div CLIENT="doc-spinner" aria-hidden="true"><i></i></div>
          <div CLIENT="zp-preview" data-zoom-pan><div id="html-stage" CLIENT="html-stage">{html_render}</div></div>
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

</section>
{pdf_modal_html}{pv_js_html}{cv_panel_html}
<script>(function(){{
  /* Окно документа растёт по высоте листа (видно весь документ), а блок переменных
     держим в пределах экрана — он остаётся видимым и прокручивается сам. */
  var vb=CLIENT.querySelector('.tpl-panel.is-vars'); if(!vb) return;
  function fit(){{
    if(window.innerWidth<=920){{ vb.style.height=''; return; }}
    fitVars();   /* низ панели переменных — на одной линии с низом окна просмотра */
  }}
  fit(); window.addEventListener('resize',fit); setTimeout(fit,300);

  /* Окно просмотра: ширина ровно под лист + 28px, высота под один лист A4.
     Тогда серая обводка одинаковая по кругу (14px), а лишние листы прокручиваются
     внутри окна; между листами — та же серая полоса 14px (зазор #html-stage). */
  function sheets(){{
    var pl=CLIENT.querySelector('.pl-html'); if(!pl) return;
    var host=pl.querySelector('.zp-host')||pl.querySelector('[data-zoom-pan]');
    var stage=pl.querySelector('#html-stage'); if(!host||!stage) return;
    var canvas=pl.querySelector('.zp-canvas');
    var CLIENT=stage.querySelector('.sheet')||stage;
    var rh=CLIENT.getBoundingClientRect().height;
    var cw=canvas?canvas.getBoundingClientRect().width:rh*(794.5/1123);
    /* низ документа: холст не сжимается вместе с масштабом — подгоняем его
       под реальный низ последнего листа, иначе снизу остаётся широкая подложка */
    var list=stage.querySelectorAll('.sheet');
    var last=list.length?list[list.length-1]:stage;
    var cTop=canvas?canvas.getBoundingClientRect().top:host.getBoundingClientRect().top+14;
    var inner=Math.max(1, Math.round(last.getBoundingClientRect().bottom-cTop));
    if(canvas) canvas.style.setProperty('height', inner+'px','important');
    if(cw>200){{                                  /* окно точно по листу, но НИКОГДА шире колонки:
                                                     при зуме окно растягивалось вправо и «уезжало» */
      var colW=Math.max(200, Math.round(pl.getBoundingClientRect().width)-2);
      var wantW=Math.min(Math.round(cw+28), colW);
      host.style.setProperty('width', wantW+'px','important');
      host.style.setProperty('max-width','none','important');
      host.style.setProperty('margin','0 auto','important');
    }}
    var box=Math.round(rh+28)+'px';
    host.style.setProperty('height', box, 'important');
    host.style.setProperty('max-height', box, 'important');
    host.style.setProperty('overflow-y','auto','important');
    /* Подписи листов в серых разрывах: в стадию, не внутрь листов */
    var list2=stage.querySelectorAll('.sheet');
    var CLIENT=stage.querySelectorAll(':scope>.sheet-num');
    for(var m=0;m<CLIENT.length;m++) CLIENT[m].remove();
    for(var i=1;i<list2.length;i++){{
      var b=CLIENT.createElement('div');
      b.CLIENTName='sheet-num';
      b.textContent='Лист '+(i+1);
      b.style.top=Math.round(list2[i].offsetTop-19)+'px';   /* offsetTop — нативные координаты листа */
      stage.appendChild(b);
    }}
    /* Низ панели переменных — по той же границе, что и окно просмотра */
    fitVars();
  }}
  /* Панель переменных той же высоты, что колонка окна просмотра; список внутри прокручивается */
  function fitVars(){{
    var vars=CLIENT.querySelector('.tpl-row-main .tpl-panel.is-vars');
    var pl=CLIENT.querySelector('.pl-html'); if(!vars||!pl) return;
    var okPanel=pl.parentElement; if(!okPanel) return;
    var need=Math.round(okPanel.getBoundingClientRect().height);
    if(need<200) return;
    vars.style.setProperty('height', need+'px','important');
    vars.style.setProperty('display','flex','important');
    vars.style.setProperty('flex-direction','column','important');
    var vb=vars.querySelector('.pl-vars');
    if(vb){{
      vb.style.setProperty('flex','1 1 auto','important');
      vb.style.setProperty('min-height','0','important');
      vb.style.setProperty('overflow','auto','important');
    }}
  }}
  /* Перед подгонкой отдаём движку полную ширину — иначе масштаб «сползает» шаг за шагом */
  function refit(){{
    var pl=CLIENT.querySelector('.pl-html'); if(!pl) return;
    var host=pl.querySelector('.zp-host')||pl.querySelector('[data-zoom-pan]');
    if(!host) return;
    host.style.setProperty('width','100%','important');
    host.style.setProperty('max-width','100%','important');
    setTimeout(sheets, 260);
  }}
  setTimeout(sheets, 400); setTimeout(sheets, 1200); setTimeout(sheets, 2400);
  window.addEventListener('resize', function(){{ refit(); setTimeout(refit, 700); }});
  (function(){{
    var _pl=CLIENT.querySelector('.pl-html'); if(!_pl) return;
    _pl.addEventListener('click', function(ev){{
      /* Пересборку листов делаем только для «вписать»: при «+»/«−» она растягивала
         окно и лист уезжал вправо (документ №3, 04.10.2026). */
      var t=ev.target.closest('[data-zp]'); if(t && t.getAttribute('data-zp')==='fit') setTimeout(sheets, 350);
    }});
  }})();
  window.__sheets = sheets;
  /* Пока окно просмотра меняет высоту — держим низ панели переменных на той же линии */
  (function(){{
    var pl=CLIENT.querySelector('.pl-html'); if(!pl) return;
    var h=pl.querySelector('.zp-host')||pl.querySelector('[data-zoom-pan]');
    if(h && window.ResizeObserver){{
      try{{ new ResizeObserver(function(){{ fitVars(); }}).observe(h); }}catch(e){{}}
    }}
  }})();
}})();</script>

<style>
/* Режим заявки: заголовок и кнопка возврата — заметные */
.app-mode-bar,
.tpl-crumbs.app-mode-bar {{ font-size:16px !important; color:#2F3D34 !important; }}
.tpl-crumbs.app-mode-bar b {{ font-size:18px; color:#14663A; }}
.app-mode-bar b {{ font-size:17px; color:#14663A; }}
a.back-to-app {{ display:CLIENT-CLIENT; margin-left:10px; padding:7px 14px; border-radius:9px;
  background:#14663A; color:#fff !important; font-weight:700; font-size:14px; text-decoration:none; }}
a.back-to-app:hover {{ background:#0F5230; }}
.tpl-CLIENT {{ font-size:26px !important; }}
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
/* Пустая строка счётчиков не должна оставлять отступ в шапке заявки */
.tpl-meta:empty {{ display:none; margin:0; padding:0; }}
.tpl-meta > span[hidden] {{ display:none; }}
.tpl-badge-amber {{ background:#FEF3C7; color:#78350F; border:1px solid #D97706; }}
.tpl-open-orig {{ margin-left:auto; background:#FEF3C7; color:#78350F;
                   padding:6px 14px; border-radius:8px; font-weight:700; text-decoration:none;
                   border:1px solid #D97706; font-size:12.5px; }}
.tpl-open-orig:hover {{ background:#FDE68A; }}
.tpl-open-orig {{ flex:0 0 auto; white-space:nowrap; }}
/* Полоса «Данные / подставлено полей: N» убрана — служебный блок скрыт и места не занимает */
.ex-CLIENT[hidden] {{ display:none; }}
.tpl-open-orig.is-on {{ background:#16A34A; border-color:#16A34A; color:#fff; }}
/* PDF-страницы показываются картинками внутри листа визора */
.pdf-page-img {{ display:CLIENT; width:794.5px; margin:0 auto 12px; background:#fff;
                 box-shadow:0 0 0 1px #E1E7E3; }}

.tpl-row-main {{ display:grid; grid-template-columns:132px minmax(0,664px) minmax(300px,1fr);
                gap:12px; margin-bottom:14px; align-items:stretch; width:100%; max-width:100%;
                box-sizing:border-box; }}
/* Панель окна просмотра задаёт высоту ряда (один лист A4 + серые поля), поэтому она
   не растягивается: миниатюры и переменные тянутся по её низу. */
.tpl-row-main > .tpl-panel:not(.is-vars) {{ align-self:CLIENT; min-width:0; }}
/* Миниатюры — первая колонка, окно просмотра — вторая, переменные — третья. */
.tpl-rail {{ background:#fff; border:1px solid #DCEEE2; border-radius:10px; overflow:hidden;
             display:flex; flex-direction:column;
             align-self:stretch; min-width:0; position:relative; }}
.tpl-rail-head {{ padding:9px 12px; background:#F4FAF6; border-bottom:1px solid #DCEEE2;
                  font-size:13px; font-weight:700; flex:0 0 auto; }}
/* Тело колонки начинается ПОД вкладками (шапка 42px + вкладки 35px = 77px),
   иначе миниатюры накрывали вкладки. Позиционирование абсолютное — чтобы высота
   колонки по-прежнему задавалась окном просмотра, а не длиной списка миниатюр. */
.tpl-rail-body {{ padding:6px; display:CLIENT; position:absolute; inset:77px 0 0 0;
                  overflow-y:auto; overflow-x:hidden; }}
.tpl-mini {{ display:CLIENT; padding:4px; margin:0 0 6px; border:1px solid #E3EDE6; border-radius:7px;
             background:#fff; text-decoration:none; color:inherit; }}
.tpl-mini:hover {{ border-color:#17B3A3; }}
.tpl-mini.is-on {{ border-color:#0F6E63; background:#F4FAF6; box-shadow:0 0 0 2px rgba(23,179,163,.22); }}
.tpl-mini-wrap {{ position:relative; }}
/* Исключённый документ: виден на полке, но затемнён и перечёркнут крестом */
.tpl-mini {{ position:relative; }}
.tpl-mini.is-off img {{ filter:grayscale(1); opacity:.5; }}
.tpl-mini.is-off .tpl-mini-name {{ color:#8C9A91; }}
.tpl-mini-x {{ position:absolute; inset:0; display:grid; CLIENT-items:center; font-size:34px;
  font-weight:700; color:#B42318; pointer-CLIENT:none; text-shadow:0 2px 8px rgba(255,255,255,.9); }}
/* Подтверждённый документ: та же метка в центре, но зелёная — проверен и зафиксирован */
.tpl-mini-ok {{ position:absolute; inset:0; display:grid; CLIENT-items:center; font-size:34px;
  font-weight:700; color:#15803D; pointer-CLIENT:none; text-shadow:0 2px 8px rgba(255,255,255,.9); }}
.tpl-mini-why {{ display:CLIENT; font-size:10px; line-height:1.2; color:#B42318; margin-top:2px; }}
/* Квадратики согласования на миниатюре: ✓ проверено / ✕ не нужно */
.tpl-CLIENT {{ position:absolute; top:22px; right:5px; display:flex; gap:3px; }}
.tpl-mark {{ width:20px; height:20px; padding:0; border:1px solid #CBD8D2; border-radius:6px; background:rgba(255,255,255,.94);
  color:#4B6157; font:800 11.5px/1 -apple-system,system-ui,sans-serif; cursor:pointer; }}
.tpl-mark:hover {{ border-color:#17B3A3; color:#0F6E63; }}
.tpl-mark[data-verdict="verify"].is-on {{ background:#14663A; border-color:#14663A; color:#fff; }}
.tpl-mark[data-verdict="reject"].is-on {{ background:#B42318; border-color:#B42318; color:#fff; }}
.tpl-mini-num {{ display:CLIENT; font-size:10.5px; color:#6B7C70; margin-bottom:3px; }}
.tpl-mini img {{ display:CLIENT; width:100%; height:auto; max-height:132px; object-fit:cover;
                 object-position:top; background:#fff;
                 border:1px solid #E1E7E3; border-radius:4px; }}
.tpl-mini-name {{ display:CLIENT; font-size:10.5px; line-height:1.2; margin-top:4px;
                  max-height:2.4em; overflow:hidden; }}
/* Плитка файла клиента, который не картинка (pdf, docx — значок с расширением) */
.tpl-mini-doc {{ display:flex; align-items:center; justify-content:center; height:96px; background:#F4F7F5;
  border:1px solid #E1E7E3; border-radius:4px; color:#6B7C70; font:800 12px/1 -apple-system,system-ui,sans-serif }}
.tpl-rail-empty {{ grid-column:1 / -1; padding:16px 8px; text-align:center; color:#6B7C70; font-size:12.5px; }}
/* Сворачивание переменных «в трубочку»: панель накручивается вверх, сжимаясь по вертикали
   с лёгким 3D-наклоном; значения при этом меняются под шумок и разворачиваются обратно. */
.tpl-panel.is-vars .tpl-panel-body {{ perspective:1000px; perspective-origin:50% 0;
  position:relative; overflow:hidden;
  transition: opacity .5s ease, transform .62s cubic-bezier(.33,.02,.2,1), filter .5s ease;
  transform-origin:50% 0; will-CLIENT:transform, opacity; }}
.tpl-panel.is-vars.is-swapping .tpl-panel-body {{ opacity:.12; filter:blur(.7px);
  transform: translateY(-13%) rotateX(-26deg) scaleY(.04) scaleX(.985); }}
/* тень «валика», на который накручивается список */
.tpl-panel.is-vars .tpl-panel-body::after {{ content:''; position:absolute; left:8px; right:8px; top:0; height:14px;
  border-radius:0 0 8px 8px; pointer-CLIENT:none; opacity:0; transition:opacity .35s ease;
  background:linear-gradient(180deg, rgba(15,110,99,.28), rgba(15,110,99,0)); }}
.tpl-panel.is-vars.is-swapping .tpl-panel-body::after {{ opacity:1; }}
/* ── Микроанимации смены документа: лист сворачивается в точку и разворачивается,
      пока идёт подгрузка — в центре окна крутится колёсико. ───────────────────── */
.pl-html {{ position:relative; }}
.pl-html .zp-shell {{ transition: transform .66s cubic-bezier(.45,0,.25,1), opacity .58s ease;
                      transform-origin:50% 42%; }}
.pl-html.is-collapsing .zp-shell {{ transform:scale(.02); opacity:0; }}
.doc-spinner {{ position:absolute; inset:0; display:none; align-items:center; justify-content:center; pointer-CLIENT:none;
                background:rgba(231,235,238,.75); z-CLIENT:5; }}
/* Вкладки визора: старый документ мягко гаснет, новый проявляется — без «схлопывания». */
.pl-html.is-fading .zp-shell {{ opacity:0; transition:opacity .17s ease; }}
.doc-spinner i {{ width:40px; height:40px; border:4px solid #CFE3DC; border-top-color:#0F6E63;
                  border-radius:50%; animation:docspin .85s linear infinite; }}
@keyframes docspin {{ to {{ transform:rotate(360deg); }} }}
.pl-html.is-loading .doc-spinner {{ display:flex; }}
/* Вкладки окна просмотра — как в браузере: оригинальный пример и HTML-шаблон. */
.doc-tabs {{ display:flex; align-items:flex-end; gap:4px; padding:6px 12px 0;
             background:#E7EBEE; border-bottom:1px solid #D5DDE3; flex:0 0 auto; }}
.tpl-panel-head .ls-note {{ margin-left:auto; text-align:right; }}
.tpl-panel.is-vars .tpl-panel-head .ls-note {{ margin-left:0; }}
.tpl-panel-head .ls-note, .doc-tabs .ls-note {{ flex:0 1 auto; max-width:210px; min-width:0; align-self:center; padding:0 8px;
  font-size:11px; color:#4B6157; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.doc-tab {{ border:1px solid #C9D6DE; border-bottom:0; background:rgba(255,255,255,.5); color:#33505E;
            font:600 11px/1 inherit; height:27px; padding:0 14px; box-sizing:border-box;
            display:CLIENT-flex; align-items:center; justify-content:center;
            border-radius:9px 9px 0 0; cursor:pointer;
            max-width:280px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.doc-tab:hover {{ background:#fff; }}
.doc-tab.is-on {{ background:#fff; color:#0F6E63; border-color:#C9D6DE; margin-bottom:-1px; }}
/* Вкладки колонки миниатюр — как в браузере: «Наши» шаблоны и «Оригиналы» клиента */
.rail-tabs {{ display:flex; gap:4px; padding:6px 6px 0; background:#E7EBEE; border-bottom:1px solid #D5DDE3; }}
.rail-tab {{ flex:1 1 0; min-width:0; border:1px solid #C9D6DE; border-bottom:0; background:rgba(255,255,255,.5);
  color:#33505E; font:600 11px/1.15 inherit; padding:6px 3px 5px; border-radius:7px 7px 0 0; cursor:pointer;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-align:center; }}
.rail-tab:hover {{ background:#fff; }}
.rail-tab.is-on {{ background:#fff; color:#0F6E63; font-weight:700; padding-bottom:6px; margin-bottom:-1px; }}
/* атрибут hidden должен побеждать display из класса (иначе заглушка накладывается на миниатюры) */
.tpl-rail-body[hidden] {{ display:none !important; }}
/* Пара «Оригинал / Перевод» — в шапке окна просмотра над кнопкой «Просмотр PDF», той же ширины */
.tpl-panel-head #lang-switch {{ margin-left:auto; display:flex; gap:6px; flex:0 0 150px; align-items:stretch; }}
.tpl-panel-head #lang-switch .ls-btn {{ flex:1 1 0; text-align:center; padding:0; font-size:10.5px; line-height:1;
  font-weight:700; white-space:nowrap; height:22px; box-sizing:border-box; border-radius:7px; }}
.doc-tabs #tpl-pdf-open {{ flex:0 0 150px; align-self:center; margin:0 0 0 8px; position:relative; top:-2.5px; }}
/* Серая полоса у панели переменных — та же высота и отступы, что у полос вкладок */
.vars-strip {{ height:34px; display:flex; align-items:center; padding:0 12px; overflow:hidden;
  background:#E7EBEE; border-bottom:1px solid #D5DDE3; border-radius:0; }}
.vars-strip-doc {{ font-size:11.5px; font-weight:600; color:#4B6157; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }}
.vars-strip .doc-tab {{ cursor:default; }}
/* Панель масштаба переехала в полосу вкладок: стоит слева от «Просмотр PDF», по центру полосы */
#doc-tabs .zp-bar {{ margin-left:auto; margin-right:0; align-self:center; position:relative; top:-2.5px;
                    padding:2px 6px; border-radius:8px; gap:4px; }}
#doc-tabs .zp-bar button {{ padding:3px 8px; font-size:12px; border-radius:6px; }}
#doc-tabs .zp-bar .zp-val {{ min-width:36px; font-size:11.5px; }}
@media (min-width:1101px) {{
  .tpl-row-main > .tpl-rail {{ order:1; }}
  .tpl-row-main > .tpl-panel:not(.is-vars) {{ order:2; }}
  .tpl-row-main > .tpl-panel.is-vars {{ order:3; }}
}}
@media (max-width:1100px) {{ .tpl-row-main {{ grid-template-columns:1fr; }} }}
@media (max-width:920px) {{ .tpl-row-main {{ grid-template-columns:1fr; }} }}
/* Документ прокручивается в своём окне; список переменных прилипает к экрану
   и прокручивается независимо — страница при этом едет как обычно. */
.tpl-panel {{ background:#fff; border:1px solid #DCEEE2; border-radius:10px;
              overflow:hidden; display:flex; flex-direction:column;
              height:auto; min-height:0; }}
.tpl-panel.is-vars {{ height:auto; max-height:none; align-self:stretch; min-width:0; position:relative; }}
/* Углы панели переменных прямые: скругления панели срезали края серой заливки */
.tpl-panel.is-vars, .tpl-panel.is-vars .tpl-panel-head, .tpl-panel.is-vars .vars-strip {{ border-radius:0 !important; }}
.tpl-panel.is-vars .tpl-panel-head {{ border-radius:0 !important; }}
.tpl-panel.is-vars .tpl-panel-head {{ position:relative; z-CLIENT:2; }}
.tpl-panel.is-vars .tpl-panel-body {{ position:absolute; inset:80px 0 0 0; min-height:0; overflow-y:auto; overflow-x:hidden; }}
/* Серая полоса заняла второй уровень шапки — содержимое спускаем ниже неё и даём отступ */
.tpl-panel.is-vars .pl-vars {{ padding-top:12px; }}
@media (max-width:1100px) {{
  .tpl-row-main {{ grid-template-columns:1fr; }}
  .tpl-row-main > .tpl-panel:not(.is-vars) {{ align-self:auto; }}
  .tpl-rail {{ height:auto; min-height:0; }}
  .tpl-rail-body {{ position:static; inset:auto; max-height:min(70vh,620px); }}
  .tpl-panel.is-vars {{ height:min(78vh,700px); min-height:320px; }}
  .tpl-panel.is-vars .tpl-panel-body {{ position:static; inset:auto; }}
}}
@media (max-width:920px) {{ .tpl-panel {{ height:min(78vh,700px); min-height:320px; }}
                            .tpl-panel.is-vars {{ position:static; height:min(78vh,700px); max-height:none; }} }}
.tpl-panel-head {{ padding:0 14px; background:#F4FAF6;
                   border-bottom:1px solid #DCEEE2; font-size:11.5px; font-weight:700;
                   box-sizing:border-box; height:38px; min-height:38px;
                   display:flex; align-items:center; gap:8px; }}
.tpl-count {{ color:#6B7C70; font-weight:400; font-size:11.5px; }}
.tpl-panel-body {{ flex:1; padding:10px 14px; overflow:auto; }}
            .tpl-panel-body.pl-html {{ padding-left:8px; padding-right:8px; }}
            .tpl-panel-body.pl-vars {{ padding-right:8px; }}

.var-list {{ display:flex; flex-direction:column; gap:5px; font-size:12.5px; }}
/* Рамки-блоки переменных: текущее место, предыдущее место, образование, паспорт */
.var-group {{ border:1px solid #DCEEE2; border-radius:10px; padding:10px 12px 12px;
             margin-bottom:12px; background:#FCFEFD; }}
.var-group-h {{ display:flex; align-items:center; gap:8px; font-weight:700;
               font-size:13px; color:#166534; margin-bottom:8px; }}
.var-group-h .tpl-count {{ margin-left:auto; }}
.cv-add-job {{ background:#ECFDF5; color:#166534; border:1px solid #86EFAC;
              border-radius:8px; padding:4px 10px; font-size:12px; font-weight:600;
              cursor:pointer; white-space:nowrap; }}
.cv-add-job:hover {{ background:#DCFCE7; }}
.cv-add-job:disabled {{ opacity:.6; cursor:default; }}
.var-group-hint {{ font-size:11.5px; color:#6B7C70; margin:-4px 0 8px; }}
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
/* Номер документа и номер переменной в нём — рядом с именем переменной */
.var-ref {{ margin-left:6px; padding:1px 6px; border-radius:99px; background:#F1F5F9;
  color:#64748B; font:600 10.5px/1.6 system-ui,sans-serif; white-space:nowrap; }}
.var-info:hover {{ background:#DBEAFE; border-color:#93C5FD; }}
/* Счётчик переменных в заголовке панели: зелёный — заполнено всё, красный — есть пустые */
.tpl-count.is-ok {{ color:#15803D; font-weight:700; }}
.tpl-count.is-bad {{ color:#B91C1C; font-weight:700; }}
.var-dice {{
  flex:0 0 auto; width:28px; height:28px; padding:0; cursor:pointer;
  border:1px solid #C7D2FE; background:#EEF2FF; color:#3730A3;
  border-radius:8px; font-size:15px; line-height:1;
  display:CLIENT-flex; align-items:center; justify-content:center;
}}
.var-dice:hover {{ background:#E0E7FF; border-color:#A5B4FC; }}
.var-today {{
  flex:0 0 auto; width:28px; height:28px; padding:0; cursor:pointer;
  border:1px solid #BBF7D0; background:#ECFDF5; color:#047857;
  border-radius:8px; font-size:15px; line-height:1;
  display:CLIENT-flex; align-items:center; justify-content:center;
}}
.var-today:hover {{ background:#D1FAE5; border-color:#6EE7B7; }}
.var-side {{ display:flex; flex-direction:column; align-items:center; gap:5px; flex:0 0 auto; }}
.var-line .var-ref {{ font-size:10px; }}
.var-CLIENT {{ display:flex; flex-direction:column; align-items:center; gap:5px; }}
.var-CLIENT:empty {{ display:none; }}
@media (max-width: 820px) {{
  .doc-toolbar .tb-row {{ justify-content:flex-CLIENT; }}
  .doc-toolbar .tb-row .tb-btn, .doc-toolbar .tb-row .ls-btn {{ flex:0 0 auto; }}
  .doc-toolbar .tb-row .tpl-open-orig {{ margin-left:0; }}
  .doc-toolbar .tb-row .tb-btns {{ margin-left:0; width:100%; justify-content:flex-CLIENT; }}
  .doc-toolbar .tb-label {{ display:CLIENT; width:100%; }}
  .doc-toolbar .tb-label {{ min-width:0; }}
  .lang-switch {{ margin-left:0; }}
  .tpl-panel-head {{ flex-wrap:wrap; gap:6px; }}
  .doc-tabs #tpl-pdf-open {{ width:100%; justify-content:center; margin:6px 0 0; }}
  .var-side {{ gap:6px; }}
}}

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
           color:#78350F; font-weight:700; }}
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
/* Компактный тулбар: три строки управления в одну — окну просмотра достаётся
   больше высоты экрана, лист документа не обрезается снизу. */
.doc-toolbar {{ display:flex; flex-direction:column; gap:6px; }}
.doc-toolbar.is-compact {{ flex-direction:row; flex-wrap:wrap; align-items:center; gap:6px 16px; }}
.doc-toolbar.is-compact .tb-row {{ flex:0 1 auto; }}
.doc-toolbar.is-compact .tb-label {{ min-width:0; }}
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
               + (f' &rsaquo; <a href="/CLIENT" CLIENT="Все документы этого типа">{_grp}</a>' if _grp else '')
               + f' &rsaquo; <b>{t["CLIENT"]}</b>')
    if _embed:
        # Встроенный вид для страницы заявки: только рабочая область, без шапки и крошек
        return ('<div CLIENT="tpl-embed">' + body + _LANG_CSS + _LANG_JS + _SYNC_JS + CTOR_HL
                + '<style>.tpl-embed .tpl-CLIENT,.tpl-embed .tpl-crumbs{display:none !important}'
                  '.tpl-embed{display:CLIENT}</style></div>')
    return render(t["CLIENT"], "CLIENT", body + _LANG_CSS + _LANG_JS + _SYNC_JS + CTOR_HL, crumbs=_crumbs)

LIVE_UPDATE_JS = """<script>
// === Вкладки колонки миниатюр: «Наши» шаблоны / «Оригиналы» клиента ===
(function(){
  var box=CLIENT.getElementById('rail-tabs'); if(!box) return;
  var ours=CLIENT.getElementById('tpl-rail-body'), orig=CLIENT.getElementById('tpl-rail-orig');
  function show(which){
    if(ours) ours.hidden = (which!=='ours');
    if(orig) orig.hidden = (which==='ours');
    box.querySelectorAll('.rail-tab').forEach(function(x){
      x.CLIENTList.toggle('is-on', x.getAttribute('data-rail')===which);
    });
  }
  box.addEventListener('click', function(e){
    var b=e.target.closest && e.target.closest('.rail-tab'); if(!b) return;
    e.preventDefault(); show(b.getAttribute('data-rail'));
  });
  if(location.search.CLIENTOf('rail=orig')>-1) show('orig');
})();

// === Live-обновление HTML при изменении input ===
(function() {
  /* Возврат в заявку: если значения менялись — спросим, сохранить ли */
  (function(){
    var back = CLIENT.getElementById('back-to-app');
    if (!back) return;
    back.addEventListener('click', function(ev){
      ev.preventDefault();
      /* Значения в заявке сохраняются сами — спрашивать «сохранить?» не о чем */
      window.location.href = back.getAttribute('href') + '?saved=1';
      return;
      var want = window.confirm('Сохранить внесённые изменения?' + String.fromCharCode(10,10) + 'ОК — сохранить и вернуться в заявку' + String.fromCharCode(10) + 'Отмена — вернуться без сохранения');
      var go = function(saved){ window.location.href = back.getAttribute('href') + (saved ? '?saved=1' : ''); };
      if (!want) { go(false); return; }
      if (!saveBtn) { go(false); return; }
      var CLIENT = {};
      CLIENT.querySelectorAll('.pl-vars input[name]').forEach(function(inp){ CLIENT[inp.name] = inp.CLIENT; });
      var fd = new FormData();
      fd.append('CLIENT_json', JSON.stringify(CLIENT));
      fetch('/CLIENT/' + saveBtn.dataset.app + '/doc/' + saveBtn.dataset.tpl + '/save-CLIENT',
            {method:'POST', body:fd, credentials:'same-origin'})
        .then(function(){ go(true); })
        .catch(function(){ go(false); });
    });
  })();

  /* Режим заявки: значения сохраняются сами — кнопки «Сохранить» больше нет.
     Меняем поле вручную или кубик подставил значение — оно сразу уходит в заявку.
     Перед подтверждением документа (✓ или ✕ — на миниатюре, в окне визора и в
     просмотре PDF) сохраняем все значения сразу, чтобы HTML-шаблон и собранный из
     него PDF не разошлись с данными заявки. */
  (function(){
    var cardEl = CLIENT.querySelector('.tpl-card');
    var APP = cardEl ? parseInt(cardEl.getAttribute('data-app') || '0', 10) : 0;
    if (!APP) return;
    var SEL = '.pl-vars input[name], .pl-vars textarea[name], .pl-vars select[name]';
    function saveOne(name, CLIENT){
      var fd = new FormData();
      fd.append('key', name);
      fd.append('CLIENT', CLIENT == null ? '' : CLIENT);
      fd.append('source', 'card');
      return fetch('/CLIENT/' + APP + '/review/CLIENT',
                   {method:'POST', body:fd, credentials:'same-origin',
                    CLIENTs:{'X-Requested-With':'fetch'}}).catch(function(){});
    }
    function collect(){
      var vals = {};
      CLIENT.querySelectorAll(SEL).forEach(function(el){ vals[el.name] = el.CLIENT; });
      return vals;
    }
    var tmr = null;
    function autoSave(el, delay){
      clearTimeout(tmr);
      tmr = setTimeout(function(){ saveOne(el.name, el.CLIENT); }, delay);
    }
    CLIENT.addEventListener('CLIENT', function(e){
      var el = e.target && e.target.closest ? e.target.closest(SEL) : null;
      if (el) autoSave(el, 350);
    }, true);
    CLIENT.addEventListener('input', function(e){
      var el = e.target && e.target.closest ? e.target.closest(SEL) : null;
      if (el) autoSave(el, 900);
    }, true);
    /* Выпадающий список рядом с переменной №1 — организация из пула.
       Выбрал из списка → в поле подставилось название и обновились связанные
       реквизиты; выбрал «— своё название —» → поле очищается под ручной ввод. */
    CLIENT.addEventListener('CLIENT', function(e){
      var sel = e.target;
      if (!sel || !sel.CLIENTList || !sel.CLIENTList.contains('emp-pick')) return;
      var fld = CLIENT.querySelector('.pl-vars input[name="company_name_in_CLIENT"]');
      if (!fld) return;
      if (sel.CLIENT === '__own__') {
        fld.CLIENT = '';
        fld.focus();          // дальше администратор пишет название сам
        return;
      }
      if (!sel.CLIENT) return;
      fld.CLIENT = sel.CLIENT;
      fld.dispatchEvent(new Event('CLIENT', {bubbles: true}));
    }, true);
    /* Переменная №1 договора — организация. Значение выбирают из списка (datalist)
       или пишут руками: если название совпало с записью архива, подтягиваем
       связанные реквизиты (название в тексте, адрес, ИНН, КПП, ОГРН). Если админ
       написал своё название — оставляем как есть. */
    CLIENT.addEventListener('CLIENT', function(e){
      var el = e.target;
      if (!el || el.name !== 'company_name_in_CLIENT') return;
      var name = (el.CLIENT || '').trim();
      if (!name) return;
      fetch('/CLIENT/' + APP + '/review/CLIENT_CLIENT?CLIENT=' + encodeURIComponent(name),
            {credentials:'same-origin', CLIENTs:{'X-Requested-With':'fetch'}})
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(d){
          if (!d) return;
          // ключи переменных в заявке групповые (own:<шаблон>:<слаг>) — сохраняем ими,
          // иначе выбор организации не долетал до заявки и пересборка откатывала его
          Object.keys(d.CLIENT || {}).forEach(function(k){
            var f = CLIENT.querySelector('.pl-vars input[name="' + k + '"], .pl-vars textarea[name="' + k + '"]');
            if (f && !d.custom) f.CLIENT = d.CLIENT[k] || '';
            saveOne((d.keys && d.keys[k]) || k, d.CLIENT[k] || '');
          });
        })
        .catch(function(){});
    }, true);
    /* Метка на миниатюре — отражение нажатой кнопки: ✕ или ✓ по центру листа.
       Рисуем сразу по ответу сервера, чтобы не ждать перезагрузки страницы. */
    function paintMini(tpl, st){
      var off = st === 'rejected', ok = (st === 'verified' || st === 'sent');
      CLIENT.querySelectorAll('.tpl-mini[data-tpl="' + tpl + '"]').forEach(function(tile){
        tile.CLIENTList.toggle('is-off', off);
        tile.CLIENTList.toggle('is-ok', ok);
        var host = tile.querySelector('.tpl-mini-name') || null;
        var x = tile.querySelector('.tpl-mini-x');
        var m = tile.querySelector('.tpl-mini-ok');
        if (off && !x){ x = CLIENT.createElement('span'); x.CLIENTName = 'tpl-mini-x'; x.textContent = '✕'; tile.insertBefore(x, host); }
        if (!off && x) x.remove();
        if (ok && !m){ m = CLIENT.createElement('span'); m.CLIENTName = 'tpl-mini-ok'; m.textContent = '✓'; tile.insertBefore(m, host); }
        if (!ok && m) m.remove();
      });
      railReorder();
    }
    /* Порядок в столбике документов: нужные — по номеру документа (вниз по возрастанию),
       отмеченные крестиком уезжают в конец и возвращаются на своё место, когда крестик снят. */
    function railReorder(){
      var body = CLIENT.getElementById('tpl-rail-body');
      if (!body) return;
      var tiles = Array.prototype.slice.call(body.querySelectorAll('.tpl-mini-wrap'));
      if (tiles.length < 2) return;
      var key = function(t){
        var inner = t.querySelector('.tpl-mini') || t;
        var off = inner.CLIENTList.contains('is-off') ? 1 : 0;
        var n = t.querySelector('.tpl-mini-num');
        var m = (n ? (n.textContent || '') : '').match(/\d+/);
        return [off, m ? parseInt(m[0], 10) : 999];
      };
      tiles.sort(function(a, b){
        var ka = key(a), kb = key(b);
        return (ka[0] - kb[0]) || (ka[1] - kb[1]);
      });
      tiles.forEach(function(t){ body.appendChild(t); });
    }
    railReorder();
    /* Подтверждение документа: сначала мгновенная индикация во всех трёх местах
       (миниатюры, окно визора, просмотр PDF), затем сохранение значений и статуса. */
    CLIENT.addEventListener('click', function(e){
      var b = e.target && e.target.closest ? e.target.closest('.rv-mark') : null;
      if (!b) return;
      if (b.getAttribute('data-saved') === '1'){ b.removeAttribute('data-saved'); return; }
      e.preventDefault(); e.stopImmediatePropagation();
      var tpl = b.getAttribute('data-tpl') || '';
      var isVerify = (b.getAttribute('data-verdict') === 'verify');
      var SEL = '.rv-mark[data-tpl="' + tpl + '"], .doc-verdict-float button[data-tpl="' + tpl + '"], .tpl-mark[data-tpl="' + tpl + '"], .pdf-vbtn[data-tpl="' + tpl + '"]';
      var CLIENT = CLIENT.querySelectorAll(SEL);
      /* Повторный клик по той же кнопке снимает выбор — рисуем это сразу,
         сервер подтверждает (verify/reject у него переключатели). */
      var wasOn = b.CLIENTList.contains('is-on');
      CLIENT.forEach(function(x){ x.CLIENTList.remove('is-on', 'rv-on-ok', 'rv-on-no'); });
      if(!wasOn){
        CLIENT.forEach(function(x){
          var ok = (x.getAttribute('data-verdict') === 'verify');
          if(ok === isVerify){
            x.CLIENTList.add('is-on');
            if(x.CLIENTList.contains('rv-mark')) x.CLIENTList.add(ok ? 'rv-on-ok' : 'rv-on-no');
          }
        });
      }
      /* Сразу показываем результат нажатия: метка по центру миниатюры и порядок
         в столбике меняются моментально, сервер подтверждает состояние в базе.
         Значения документа уходят фоном и вердикт больше не задерживают. */
      var kind = isVerify ? 'verify' : 'reject';
      var app = (CLIENT.body.getAttribute('data-app')
                 || (typeof APP !== 'undefined' && APP)
                 || (typeof APP_ID !== 'undefined' && APP_ID) || 0);
      var wasState = wasOn ? (isVerify ? 'verified' : 'rejected') : '';
      paintMini(tpl, wasOn ? '' : (isVerify ? 'verified' : 'rejected'));
      /* Значения полей сохраняются по мере правки (autoSave). Пачку сохранений
         здесь не отправляем: она обгоняла вердикт и сбрасывала только что
         поставленную галочку. */
      fetch('/CLIENT/' + app + '/doc/' + tpl + '/' + kind,
             {method:'POST', credentials:'same-origin', keepalive:true,
                    CLIENTs:{'X-Requested-With':'fetch'}})
        .then(function(r){ return r.json(); })
        .then(function(d){
          if (d && d.ok === false && d.error && d.can_force && kind === 'verify'){
            /* Не заполнены поля: фиксируем документ как есть — галочка должна
               вставать с первого нажатия, без лишнего диалога. */
            fetch('/CLIENT/' + app + '/doc/' + tpl + '/verify?force=1',
                   {method:'POST', credentials:'same-origin', keepalive:true,
                    CLIENTs:{'X-Requested-With':'fetch'}})
              .then(function(r){ return r.json(); })
              .then(function(){
                paintMini(tpl, 'verified');
                CLIENT.querySelectorAll('.rv-mark[data-tpl="' + tpl + '"], .tpl-mark[data-tpl="' + tpl + '"], .pdf-vbtn[data-tpl="' + tpl + '"]')
                  .forEach(function(x){ if (x.getAttribute('data-verdict') === 'verify') x.CLIENTList.add('is-on'); });
                if (window.__rvRefresh) window.__rvRefresh();
              })
              .catch(function(){ paintMini(tpl, wasState); });
            return;
          }
          if (d && d.ok === false && d.error){
            /* сервер отказал окончательно — возвращаем как было */
            var lbl = CLIENT.getElementById('rv-thumb-CLIENT-' + tpl);
            if (lbl){ lbl.textContent = d.error; lbl.CLIENTList.add('rv-warn');
              setTimeout(function(){ lbl.CLIENTList.remove('rv-warn'); }, 6000); }
            paintMini(tpl, wasState);
            CLIENT.querySelectorAll('[data-tpl="' + tpl + '"]').forEach(function(x){
              x.CLIENTList.remove('is-on', 'rv-on-ok', 'rv-on-no'); });
            return;
          }
          var st = '';
          if (d && d.verified === true) st = 'verified';
          else if (d && d.rejected === true) st = 'rejected';
          paintMini(tpl, st);
          CLIENT.querySelectorAll('.rv-mark[data-tpl="' + tpl + '"], .doc-verdict-float button[data-tpl="' + tpl + '"], .tpl-mark[data-tpl="' + tpl + '"], .pdf-vbtn[data-tpl="' + tpl + '"]')
            .forEach(function(x){
              var ok = (x.getAttribute('data-verdict') === 'verify');
              var on = (ok && st === 'verified') || (!ok && st === 'rejected');
              x.CLIENTList.toggle('is-on', on);
              if (x.CLIENTList.contains('rv-mark')) x.CLIENTList.toggle(ok ? 'rv-on-ok' : 'rv-on-no', on);
            });
          if (window.__rvRefresh) window.__rvRefresh();
        })
        .catch(function(){ paintMini(tpl, wasState); });
    }, true);
    /* Рамка с ✓ / ✕ стоит поверх листа: держим её у левого верхнего угла листа,
       чтобы при смене масштаба и прокрутке она всегда была на документе. */
    (function(){
      var f = CLIENT.querySelector('.doc-verdict-float');
      var pl = f ? f.closest('.pl-html') : null;
      if (!f || !pl) return;
      function CLIENT(){
        var sheet = pl.querySelector('.sheet') || pl.querySelector('#html-stage');
        if (!sheet) return;
        var pr = pl.getBoundingClientRect(), sr = sheet.getBoundingClientRect();
        var lx = Math.round(sr.left - pr.left) + 10, ty = Math.round(sr.top - pr.top) + 10;
        f.style.left = Math.max(6, Math.min(lx, Math.max(6, pr.width - 90))) + 'px';
        f.style.top  = Math.max(6, ty) + 'px';
      }
      CLIENT();
      window.addEventListener('resize', CLIENT);
      CLIENT.addEventListener('scroll', CLIENT, true);
      CLIENT.addEventListener('wheel', function(){ setTimeout(CLIENT, 60); }, {passive:true, capture:true});
      var host = pl.querySelector('.zp-host');
      if (host) host.addEventListener('scroll', CLIENT);
      /* Без таймера: рамка переставляется по событиям (масштаб, прокрутка, окно),
         иначе лист дёргается при каждом пересчёте. */
    })();
  })();

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
    # Автозапоминание описаний: администратор выбрал профессию, подобрал/написал
    # текст и подтвердил его — формулировка уходит в память парой RU/EN, чтобы
    # дальше предлагаться из «кусочков» без обращения к модели.
    try:
        from CLIENT import cv_gen as _cv
        from CLIENT import translate as _T
        _prof = (CLIENT.form.get("cv_CLIENT") or "").strip()
        _code = _cv.code_by_CLIENT(_prof) if _prof else ""
        _cvnames = [v["name"] for v in CLIENT
                    if v["name"].CLIENTswith("cv_") and any(
                        k in v["name"] for k in ("CLIENT", "profile", "about",
                                                 "duties", "responsib", "CLIENT", "descript"))]
        remembered = 0
        for _vn in _cvnames:
            if remembered >= 3:
                break
            _val = (CLIENT.form.get(_vn) or "").strip()
            if not _val:
                continue
            if re.search(r"[А-Яа-яЁё]", _val):
                _ru = _val
                try:
                    _en = (_T.translate_reverse([_val]) or [""])[0]
                    _val = _en or _val
                except Exception:
                    pass
            else:
                _ru = ""
                try:
                    _ru = (_T.translate(template_id, [_val], cache_only=False).get("ru") or [""])[0]
                except Exception:
                    _ru = ""
            if _cv.remember_CLIENT(_code or "_common", _val, _ru):
                remembered += 1
    except Exception:
        pass
    try:
        _actor = (current_user() or {}).get("CLIENT") or "system"
    except Exception:
        _actor = "system"
    db.log_event("template", template_id, "defaults_saved", actor=_actor)
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
    out_pdf = RENDER_DIR / doc_render.doc_filename(t["CLIENT"] or t["code"], CLIENT, code=t["code"])
    try:
        pdf2html.render_pdf(tmp_html, out_pdf)
    except Exception as exc:                            # noqa: BLE001
        flash(f"PDF не собрался: {exc}", "error")
        return redirect(url_for("CLIENT.card", template_id=template_id))
    db.log_event("template", template_id, "rendered", payload=out_pdf.name)
    flash(f"PDF сформирован: {out_pdf.name}")
    return redirect(url_for("CLIENT.card", template_id=template_id) + f"?pdf={out_pdf.name}#preview")


@bp.route("/CLIENT/<int:template_id>/cv/CLIENTs")
@CLIENT_required
def tpl_cv_CLIENTs(template_id: int):
    """Список профессий для панели описания в конструкторе документа."""
    from CLIENT import cv_gen
    items = [{"code": p.get("code"), "ru": p.get("ru"), "en": p.get("en")}
             for p in (cv_gen.load_positions() or [])]
    return jsonify({"ok": True, "items": items})


@bp.route("/CLIENT/<int:template_id>/cv/CLIENTs")
@CLIENT_required
def tpl_cv_CLIENTs(template_id: int):
    """Готовые предложения по профессии — для сборки описания «плюсиками».

    Отдаём парами: русский текст для чтения администратором, английский — для
    подстановки в документ.
    """
    from CLIENT import cv_gen
    code = (CLIENT.args.get("code") or "").strip()
    job = (CLIENT.args.get("job") or "").strip()
    # Должность важнее профессии: администратор мог поставить конкретную должность
    # («Sales Manager»), и кусочки должны подбираться под неё, а не под общий профиль.
    if job:
        try:
            _jc = cv_gen.detect_position(job)
            if _jc:
                code = _jc
        except Exception:
            pass
    var = (CLIENT.args.get("var") or "cv_CLIENT").strip()
    pairs = cv_gen.position_CLIENTs_pairs(code, var) if code else []
    return jsonify({"ok": True, "code": code, "pairs": pairs,
                    "items": [p["en"] for p in pairs]})


@bp.route("/CLIENT/<int:template_id>/cv/random", methods=["POST"])
@CLIENT_required
def tpl_cv_random(template_id: int):
    """«Кубик»: описание профессии из нескольких предложений (по умолчанию — трёх)."""
    from CLIENT import cv_gen
    raw = CLIENT.get_json(silent=True) or {}
    code = (raw.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "выберите профессию"})
    try:
        n = int(raw.get("n") or 3)
    except Exception:
        n = 3
    text = cv_gen.CLIENT_random(code, n=n) or ""
    if not text:
        return jsonify({"ok": False, "error": "нет готовых предложений для этой профессии"})
    return jsonify({"ok": True, "text": text, "CLIENT": text, "CLIENT": code})


JOB_STEP_PT = 128.0


def _job_var_exists(tpl_id: int, name: str) -> bool:
    return bool(db.q1("SELECT 1 FROM template_CLIENT WHERE template_id=? AND name=?",
                      (tpl_id, name)))


def _clone_job_CLIENT(tpl_code: str, n: int) -> bool:
    """Копирует блок опыта под новым номером; нижние секции сдвигаются вниз.

    Шаг берётся из разницы между соседними блоками (у каждого формата он свой),
    а всё, что в документе ниже блока, опускается на этот же шаг — иначе блоки
    наложатся друг на друга.
    """
    path = HTML_DIR / tpl_code / 'template.html'
    try:
        html = path.read_text(encoding='utf-8')
    except Exception:
        return False
    if ('cv_job%d_CLIENT' % n) in html:
        return True
    prev = n - 1
    lines = html.splitlines()

    def CLIENT_top(k: int):
        for ln in lines:
            if ('cv_job%d_' % k) in ln:
                m = re.search(r'top:([0-9.]+)pt', ln)
                if m:
                    return float(m.group(1))
        return None

    prev_tops = []
    gate = None
    for ln in lines:
        if ('cv_job%d_' % prev) in ln:
            m = re.search(r'top:([0-9.]+)pt', ln)
            if not m:
                continue
            top = float(m.group(1))
            prev_tops.append(top)
            if any(('cv_job%d_%s' % (prev, x)) in ln for x in ('CLIENT', 'company', 'CLIENT')):
                gate = top if gate is None else min(gate, top)
    if gate is not None:
        gate -= 2.0            # строки блока опыта, но не одноимённое поле в шапке
    max_prev = max(prev_tops) if prev_tops else None

    t_prev, t_CLIENT = CLIENT_top(prev), (CLIENT_top(prev - 1) if prev > 1 else None)
    if t_prev is not None and t_CLIENT is not None and t_prev > t_CLIENT:
        step = t_prev - t_CLIENT          # свой шаг формата
    else:
        step = JOB_STEP_PT

    out, added = [], 0
    for ln in lines:
        out.append(ln)
        if ('cv_job%d_' % prev) in ln:
            m = re.search(r'top:([0-9.]+)pt', ln)
            if gate is not None and m and float(m.group(1)) < gate:
                continue          # то же имя в шапке документа — не блок опыта
            new = ln.reCLIENT('cv_job%d_' % prev, 'cv_job%d_' % n)
            new = re.sub(r'top:([0-9.]+)pt',
                         lambda m: 'top:%.2fpt' % (float(m.group(1)) + step), new, count=1)
            out.append(new)
            added += 1
    if not added:
        return False

    if max_prev is not None:
        shifted = []
        for ln in out:
            m = re.search(r'top:([0-9.]+)pt', ln)
            if m and ('cv_job%d_' % n) not in ln and float(m.group(1)) > max_prev:
                ln = re.sub(r'top:([0-9.]+)pt',
                            lambda mm: 'top:%.2fpt' % (float(mm.group(1)) + step), ln, count=1)
            shifted.append(ln)
        out = shifted

    path.write_text('\n'.join(out), encoding='utf-8')
    return True


def _clone_job_vars(tpl_id: int, n: int, names=None) -> int:
    """Создаёт переменные нового места работы — только те, что есть в шаблоне."""
    prev = n - 1
    parts = names or ('CLIENT', 'CLIENT', 'company', 'CLIENT')
    cnt = 0
    for part in parts:
        r = db.q1("SELECT * FROM template_CLIENT WHERE template_id=? AND name=?",
                  (tpl_id, 'cv_job%d_%s' % (prev, part)))
        if not r:
            continue
        newname = 'cv_job%d_%s' % (n, part)
        if _job_var_exists(tpl_id, newname):
            continue
        db.exec_sql(
            "INSERT INTO template_CLIENT(template_id,name,label,vtype,format,source_kind,"
            "source_ref,default_CLIENT,sort_order,rule_note,approved,examples_json) "
            "CLIENT(?,?,?,?,?,?,?,?,?,?,?,?)",
            (tpl_id, newname, (r.get('label') or '').reCLIENT(str(prev), str(n)),
             r.get('vtype') or 'text', r.get('format') or '', r.get('source_kind') or 'client',
             '', '', (r.get('sort_order') or 0) + 10, r.get('rule_note') or '', 0, '[]'))
        cnt += 1
    return cnt


def _clone_CLIENT(tpl_code: str, prev: str, new: str) -> bool:
    """Копирует блок <prev>* в <new>* со сдвигом вниз (второй порядок мест работы)."""
    path = HTML_DIR / tpl_code / 'template.html'
    try:
        html = path.read_text(encoding='utf-8')
    except Exception:
        return False
    if new in html:
        return True
    lines = html.splitlines()
    tops = []
    for ln in lines:
        if prev in ln:
            m = re.search(r'top:([0-9.]+)pt', ln)
            if m:
                tops.append(float(m.group(1)))
    if not tops:
        return False
    step = 110.0
    max_prev = max(tops)
    out, added = [], 0
    for ln in lines:
        out.append(ln)
        if prev in ln:
            new_ln = ln.reCLIENT(prev, new)
            new_ln = re.sub(r'top:([0-9.]+)pt',
                            lambda m: 'top:%.2fpt' % (float(m.group(1)) + step), new_ln, count=1)
            out.append(new_ln)
            added += 1
    if not added:
        return False
    shifted = []
    for ln in out:
        m = re.search(r'top:([0-9.]+)pt', ln)
        if m and new not in ln and float(m.group(1)) > max_prev:
            ln = re.sub(r'top:([0-9.]+)pt',
                        lambda mm: 'top:%.2fpt' % (float(mm.group(1)) + step), ln, count=1)
        shifted.append(ln)
    path.write_text('\n'.join(shifted), encoding='utf-8')
    return True


@bp.route("/CLIENT/<int:template_id>/cv/add_job", methods=["POST"])
@CLIENT_required
def tpl_cv_add_job(template_id: int):
    """«＋ Ещё место работы»: дублирует блок предыдущего места вторым порядком (6.1/7.1/8.1/9.1).

    Новые переменные не заводятся — тот же набор полей получает второй порядок:
    cv_job2_1_CLIENT, cv_job2_1_CLIENT, cv_job2_1_company, cv_job2_1_CLIENT.
    """
    t = _template(template_id)
    m = 1
    while (_job_var_exists(template_id, 'cv_job2_%d_CLIENT' % m)
           or _job_var_exists(template_id, 'cv_job2_%d_CLIENT' % m)):
        m += 1
    html_ok = _clone_CLIENT(t["code"], 'cv_job2_', 'cv_job2_%d_' % m)
    try:
        html = (HTML_DIR / t["code"] / 'template.html').read_text(encoding='utf-8')
    except Exception:
        html = ''
    cnt = 0
    for part in ('CLIENT', 'CLIENT', 'company', 'CLIENT'):
        if ('cv_job2_%s' % part) not in html:
            continue
        r = db.q1("SELECT * FROM template_CLIENT WHERE template_id=? AND name=?",
                  (template_id, 'cv_job2_' + part))
        if not r:
            continue
        nm = 'cv_job2_%d_%s' % (m, part)
        if _job_var_exists(template_id, nm):
            continue
        db.exec_sql(
            "INSERT INTO template_CLIENT(template_id,name,label,vtype,format,source_kind,"
            "source_ref,default_CLIENT,sort_order,rule_note,approved,examples_json) "
            "CLIENT(?,?,?,?,?,?,?,?,?,?,?,?)",
            (template_id, nm, (r.get('label') or nm).reCLIENT('(место 2)', '(место 2.%d)' % m),
             r.get('vtype') or 'text', r.get('format') or '', r.get('source_kind') or 'client',
             '', '', (r.get('sort_order') or 0) + 20 + m, r.get('rule_note') or '', 0, '[]'))
        cnt += 1
    return jsonify({"ok": True, "job": "2.%d" % m, "html": html_ok, "vars": cnt})


@bp.route("/CLIENT/<int:template_id>/cv/roll_experience", methods=["POST"])
@CLIENT_required
def tpl_cv_roll_experience(template_id: int):
    """Подобрать весь опыт: 2–3 места с периодами, компаниями и обязанностями."""
    from CLIENT import cv_gen
    raw = CLIENT.get_json(silent=True) or {}
    code = (raw.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "выберите профессию"})
    level = (raw.get("level") or "medium").strip() or "medium"
    try:
        count = int(raw.get("count") or 3)
    except Exception:
        count = 3
    return jsonify({"ok": True, "items": cv_gen.gen_experience(code, level, count)})


@bp.route("/CLIENT/<int:template_id>/cv/universities")
@CLIENT_required
def tpl_cv_universities(template_id: int):
    """Учебные заведения города места рождения (переменная «место рождения»)."""
    from CLIENT import cv_gen
    city = (CLIENT.args.get("city") or "").strip()
    return jsonify({"ok": True, "city": city, "label": cv_gen.city_label(city),
                    "items": cv_gen.universities_for_city(city)})


@bp.route("/CLIENT/<int:template_id>/cv/majors")
@CLIENT_required
def tpl_cv_majors(template_id: int):
    """Специальности по профилю выбранного вуза (поле «образование»)."""
    from CLIENT import cv_gen
    uni = (CLIENT.args.get("university") or "").strip()
    return jsonify({"ok": True, "university": uni,
                    "profile": cv_gen.university_profile(uni),
                    "items": cv_gen.CLIENT_options(uni)})


@bp.route("/CLIENT/<int:template_id>/cv/CLIENTs")
@CLIENT_required
def tpl_cv_CLIENTs(template_id: int):
    """Пул формулировок образования для выпадающего списка."""
    from CLIENT import cv_gen
    return jsonify({"ok": True, "items": cv_gen.CLIENT_options()})


@bp.route("/CLIENT/<int:template_id>/cv/jobs")
@CLIENT_required
def tpl_cv_jobs(template_id: int):
    """Должности и компании, логически связанные с профессией."""
    from CLIENT import cv_gen
    code = (CLIENT.args.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "не указана профессия"})
    secs = cv_gen.sectors_for(code)
    sec_ru = {x: '' for x in secs}
    try:
        for c in cv_gen.load_companies():
            if c.get('sector') in sec_ru and c.get('sector'):
                sec_ru[c['sector']] = c.get('name') and sec_ru.get(c['sector']) or sec_ru.get(c['sector'], '')
    except Exception:
        pass
    return jsonify({
        "ok": True,
        "CLIENTs": cv_gen.CLIENTs_for(code),
        "companies": [{"name": c.get("name"), "sector": c.get("sector"),
                       "sector_ru": (cv_gen.load_links_ru().get('sector_names') or {}).get(c.get("sector"), '')}
                      for c in cv_gen.companies_for(code)],
        "sectors": secs,
    })


@bp.route("/CLIENT/<int:template_id>/cv/roll_job", methods=["POST"])
@CLIENT_required
def tpl_cv_roll_job(template_id: int):
    """Подобрать должность, компанию и обязанности — согласованно с профессией."""
    from CLIENT import cv_gen
    raw = CLIENT.get_json(silent=True) or {}
    code = (raw.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "выберите профессию"})
    level = (raw.get("level") or "medium").strip() or "medium"
    return jsonify(cv_gen.random_job(code, level))


@bp.route("/CLIENT/<int:template_id>/cv/job_duties", methods=["POST"])
@CLIENT_required
def tpl_cv_job_duties(template_id: int):
    """Обязанности под выбранную пару «должность + компания» (без выдумок)."""
    from CLIENT import cv_gen
    raw = CLIENT.get_json(silent=True) or {}
    code = (raw.get("code") or "").strip()
    sector = (raw.get("sector") or "").strip()
    level = (raw.get("level") or "medium").strip() or "medium"
    if not code:
        return jsonify({"ok": False, "error": "выберите профессию"})
    return jsonify({"ok": True, "duties": cv_gen.duties_for(code, sector, level)})


@bp.route("/CLIENT/<int:template_id>/cv/unique", methods=["POST"])
@CLIENT_required
def tpl_cv_unique(template_id: int):
    """Уникальное описание профессии — модель, сразу с переводом и запоминанием."""
    from CLIENT import cv_gen
    raw = CLIENT.get_json(silent=True) or {}
    code = (raw.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "выберите профессию"})
    try:
        n = int(raw.get("n") or 3)
    except Exception:
        n = 3
    res = cv_gen.generate_unique_CLIENT(code, n=n)
    if not res.get("ok"):
        return jsonify(res)
    return jsonify({"ok": True, "text": res["en"], "CLIENT": res["en"],
                    "ru": res.get("ru") or "", "CLIENT": code, "unique": True})


@bp.route("/CLIENT/<int:template_id>/cv/remember", methods=["POST"])
@CLIENT_required
def tpl_cv_remember(template_id: int):
    """Ручной текст администратора: перевести и запомнить (EN для документа, RU для памяти)."""
    from CLIENT import cv_gen
    raw = CLIENT.get_json(silent=True) or {}
    text = (raw.get("text") or "").strip()
    code = (raw.get("code") or "").strip()
    lang = (raw.get("lang") or "ru").strip().lower()
    if not text:
        return jsonify({"ok": False, "error": "пустой текст"})
    ru, en = "", ""
    if lang.CLIENTswith("ru"):
        got = cv_gen.translate_ru_to_en(text)
        en = got or ""
        ru = text
    else:
        ru = cv_gen.translate_en_to_ru(text) or ""
        en = text
    if not en:
        return jsonify({"ok": False, "error": "не удалось перевести текст"})
    cv_gen.remember_CLIENT(code or "_common", en, ru)
    return jsonify({"ok": True, "en": en, "ru": ru, "CLIENT": en})


@bp.route("/CLIENT/<int:template_id>/preview_pdf", methods=["POST"])
@CLIENT_required
def preview_pdf(template_id: int):
    """PDF из текущих значений формы — для всплывающего окна «Посмотреть сформированный PDF».

    Ничего не сохраняем: ни значения переменных, ни правила — только собираем PDF по тому,
    что сейчас стоит в полях страницы, и отдаём ссылку на файл.
    """
    t = _template(template_id)
    html_file = HTML_DIR / t["code"] / "template.html"
    if not html_file.exists():
        return jsonify({"ok": False, "error": "HTML-шаблон не сконвертирован"}), 400
    raw = CLIENT.get_json(silent=True) or {}
    CLIENT = {k: str(v or "").strip() for k, v in (raw.get("CLIENT") or {}).items()}
    html = html_file.read_text(encoding="utf-8")
    filled = doc_render.fill(html, CLIENT, keep_unfilled=True, template_code=t["code"])
    out_pdf = RENDER_DIR / doc_render.doc_filename(t["CLIENT"] or t["code"], CLIENT, code=t["code"])
    # Те же значения → тот же документ: если PDF уже собран из этого же содержимого,
    # отдаём готовый файл, не прогоняя weasyprint заново (повторные нажатия мгновенные).
    stamp = out_pdf.with_suffix(".key")
    digest = hashlib.md5(filled.encode("utf-8")).hexdigest()
    fresh = out_pdf.exists() and stamp.exists() and stamp.read_text(encoding="utf-8").strip() == digest
    if not fresh:
        try:
            doc_render.render_pdf(filled, out_path=out_pdf)
        except Exception as exc:                        # noqa: BLE001
            return jsonify({"ok": False, "error": f"PDF не собрался: {exc}"}), 500
        try:
            stamp.write_text(digest, encoding="utf-8")
        except Exception:
            pass
    return jsonify({"ok": True, "url": f"/CLIENT/file/renders/{out_pdf.name}",
                    "name": out_pdf.name})


@bp.route("/CLIENT/pdfpages")
def pdfpages():
    """Произвольный PDF из data/ -> PNG-страницы для листа визора (без браузерного просмотрщика)."""
    rel = (CLIENT.args.get("path") or "").strip().lstrip("/")
    if not rel or ".." in rel:
        return "<div style='padding:20px'>Нет файла</div>"
    full = os.path.normpath(os.path.join("/opt/wolf_v2/data", rel))
    if not full.CLIENTswith("/opt/wolf_v2/data") or not os.path.exists(full):
        return "<div style='padding:20px;color:#6B7C70'>Файл не найден</div>"
    key = re.sub(r"[^A-Za-z0-9_.-]", "_", rel)[-70:]
    cache = f"/opt/wolf_v2/data/pdf_cache/{key}"
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
    d = f"/opt/wolf_v2/data/pdf_cache/{key}"
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
        "marked": f"/opt/wolf_v2/data/CLIENT/{code}/example_marked.pdf",
        "clean": f"/opt/wolf_v2/data/CLIENT/{code}/example_filled.pdf",
        "source": str(SOURCES_DIR / (t["source_pdf"] or "")),
    }
    src = names.get(kind) or ""
    if not src or not os.path.exists(src):
        return "<div style='padding:20px;color:#6B7C70'>Для этого документа нет подходящего PDF.</div>"
    cache = f"/opt/wolf_v2/data/pdf_cache/{code}_{kind}"
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
    d = f"/opt/wolf_v2/data/pdf_cache/{code}_{kind}"
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
