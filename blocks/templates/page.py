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
from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, flash, jsonify, redirect, request, send_from_directory, url_for

from blocks.shared.layout import card as ui_card, item, modal, modal_button, render
from services import render as doc_render
from services import translate
from core import db, pdf2html
from core.auth import login_required
from core.config import BASE_DIR, HTML_DIR, MAX_UPLOAD_MB, RENDER_DIR, SOURCES_DIR
from repositories import templates as tpl_repo, variables as vars_repo

bp = Blueprint("templates", __name__)

SAFE = re.compile(r"[^A-Za-zА-Яа-я0-9._-]+")
VAR = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

# Заглушка фотографии клиента (аватарка 940×1314 px — ровно поле фото в резюме,
# 141.15 × 197.30 pt). Показывается, пока в заявке нет настоящего кадра клиента.
PHOTO_PLACEHOLDER = "/static/tpl_assets/cv_photo_placeholder.png"

STATUS_LABEL = {"ok": ("готов", "ok"), "needs_review": ("нужна проверка", "warn"),
                "draft": ("черновик", ""),
                # документ лежит на сайте, но выключен из комплектации продуктов
                "hidden": ("выключен из продуктов", "warn"),
                "merged": ("объединён с другим документом", "warn"),
                "blocked": ("закрыт", "bad")}

PRODUCT_EMOJI = {
    "C1": "🛂", "C1-EXT": "🔁", "D12": "🛃", "BRIDGING": "🌉",
    "CONV": "🔄", "E33G-NEW": "🆕", "E33G-EXT": "📈",
}

# короткие названия продуктов (как просил Андрей)
SHORT_NAME = {
    "C1":       "Виза C1",
    "C1-EXT":   "Продление C1",
    "D12":      "Виза D12",
    "BRIDGING": "Мостовая виза",
    "CONV":     "Конверсия",
    "E33G-NEW": "Виза E33G (новый)",
    "E33G-EXT": "Продление E33G",
}

# Человеческие описания продуктов — открываются кнопкой «ℹ️ Описание» в списке продуктов.
PRODUCT_INFO = {
    "C1": {
        "what": "Виза C1 (B211A, «кунджунган») — виза посещения Индонезии: туризм, встречи с партнёрами, "
                "поездки без права работы и без оформления ВНЖ.",
        "who": "Туристам, тем кто едет на разведку, посещает родственников или ведёт переговоры.",
        "term": "60 дней с момента въезда. Продлевается на месте ещё дважды — в сумме до 180 дней.",
        "docs": "Банковская справка за 3 месяца (Т-Банк или Сбер) — подтверждение платёжеспособности.",
        "flow": "Подача → справка 3 мес → виза. Самое простое оформление, спонсор и договор не нужны.",
    },
    "C1-EXT": {
        "what": "Продление визы C1 без выезда из страны.",
        "who": "Тем, кто уже в Индонезии по C1 и хочет остаться дольше 60 дней.",
        "term": "+60 дней к текущему сроку (максимум 180 дней суммарно).",
        "docs": "Банковская справка за 3 месяца.",
        "flow": "Подаётся внутри страны до окончания действующего срока пребывания.",
    },
    "D12": {
        "what": "Виза D12 «Pra-Investasi» — пред-инвестиционная виза для тех, кто планирует открывать "
                "бизнес или вкладывать средства в Индонезию.",
        "who": "Предпринимателям и инвесторам, которые готовят запуск компании на Бали/в Индонезии.",
        "term": "Многократная, срок 1–2 года (зависит от решения иммиграции).",
        "docs": "Банковская справка за 3 месяца + справка за 12 месяцев (подтверждение годового дохода), "
                "резюме (CV), Sponsor Letters — ходатайство и заявление гаранта от PT Alpha Prime Bali.",
        "flow": "Подача письма-ходатайства → проверка справок и резюме → решение. Спонсор гарантирует пребывание.",
    },
    "BRIDGING": {
        "what": "Мостовая виза (Bridging Visa 60 hari) — временный статус на 60 дней, чтобы дождаться "
                "конверсии из одной визы в другую, не выезжая из Индонезии.",
        "who": "Тем, кто уже в стране и меняет статус (например, приехал по C1, а переходит на рабочее разрешение).",
        "term": "60 дней. Не продлевается — за это время нужно оформить конверсию.",
        "docs": "Комплект писем спонсора (ходатайство + гарантия + доверенность, 3 страницы), резюме (CV), "
                "Form E-02, рабочий договор (Remote Work Agreement).",
        "flow": "Подаётся минимум за 3 дня до окончания текущего разрешения → ожидание конверсии.",
    },
    "CONV": {
        "what": "Конверсия (Alih Status) — смена статуса пребывания внутри Индонезии: обычно из Bridging Visa "
                "в KITAS E33G (рабочее разрешение удалённого работника).",
        "who": "Тем, у кого открыта мостовая виза и кто выходит в полноценный KITAS.",
        "term": "Результат — KITAS E33G (до 5 лет с продлениями). Для подачи нужен запас по текущему "
                "разрешению минимум 31 день.",
        "docs": "Комплект писем спонсора (3 страницы), резюме (CV), Form E-02 (конверсия), рабочий договор.",
        "flow": "Мостовая виза → конверсия → KITAS. Все документы от имени спонсора PT Alpha Prime Bali.",
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
        "what": "Продление KITAS E33G Remote Worker на новый срок.",
        "who": "Действующим держателям E33G, у которых заканчивается срок.",
        "term": "Продление на очередной период KITAS (до 5 лет суммарно).",
        "docs": "Банковская справка за 3 месяца, рабочий договор. Резюме не требуется.",
        "flow": "Подаётся до окончания текущего KITAS через спонсора.",
    },
}


def _safe_name(name: str) -> str:
    return SAFE.sub("_", Path(name).name) or "file"


def _short(product: dict) -> str:
    return SHORT_NAME.get(product["code"], product["name"])


def _template(template_id: int):
    row = tpl_repo.get(template_id)
    if not row:
        abort(404)
    return row


_LANG_CSS = """<style>
.lang-switch{display:inline-flex;align-items:center;gap:6px;margin-left:8px}
.lang-switch .ls-btn{border:1px solid #D8E2DC;background:#fff;border-radius:9px;padding:5px 11px;
  font-size:13px;font-family:inherit;cursor:pointer;color:#22352B}
.lang-switch .ls-btn.is-on{background:#E7F6EC;border-color:#16A34A;color:#14532D;font-weight:700}
.lang-switch .ls-note{font-size:12px;color:#6B7C70}
.zp-host[data-lang="ru"]{background:#F3F0FF}
.kv-table td.kv-row{display:block;padding:7px 0 3px;border-bottom:1px solid #EDF3EF}
/* Панель переменных — обычные блоки, без таблицы: таблица растягивалась от
   длинного значения и уводила поля вправо за пределы экрана */
.kv-table{display:block;width:100%;max-width:100%;background:#fff;border:1px solid #DCEEE2;
  border-radius:6px;overflow:hidden}
.kv-line{display:block}
.kv-row{display:block;width:100%;max-width:100%;box-sizing:border-box;padding:7px 9px 4px 8px;border-bottom:1px solid #EDF3EF}
.kv-line:last-child .kv-row{border-bottom:0}
.var-line{display:flex;align-items:center;gap:8px;min-width:0;width:100%}
.var-line input{flex:1 1 auto;min-width:0;width:100%;font-size:13.5px;padding:8px 10px;text-overflow:ellipsis}
/* Длинное значение разворачивается вниз под полем по клику — само поле не растёт */
.var-full{display:none;margin:5px 0 0 24px;font-size:12.5px;line-height:1.45;white-space:pre-wrap;
  word-break:break-word;background:#F7FAF9;border:1px solid #E1E7E3;border-radius:8px;
  padding:7px 9px;color:#24382F;max-height:220px;overflow:auto;cursor:pointer}
.var-full.is-on{display:block}
/* Цветной маркер источника значения — рядом с номером переменной:
   зелёный — взято из документов клиента, жёлтый — собрано системой, красный — не определено */
.var-mark{display:none}
/* Цветные полосы «откуда значение» скрыты по просьбе заказчика (16.10.2026):
   в окне просмотра документа зелёные/красные подчёркивания и полосы выглядят
   как правки редактора — их быть не должно, нужен чистый лист документа.
   Источник значения остаётся подписью в списке переменных. */
.kv-line.var-kind-real > .kv-row{border-left:none;background:transparent}
.kv-line.var-kind-synth > .kv-row{border-left:none;background:transparent}
.kv-line.var-kind-unknown > .kv-row{border-left:none;background:transparent}
/* Номер переменной — сразу за маркером, но не на цветной линии блока */
.var-line .kv-idx{font-size:12px;color:#87968C;flex:0 0 auto;min-width:16px;text-align:left;margin-left:1px}
/* Подпись под полем — одна строка: русское название идёт первым, длинный хвост
   («док. № · пер. № · источник») обрезается многоточием и не уезжает за край панели */
.var-name{margin:3px 0 0 8px;font-size:11.5px;color:#6B7C70;line-height:1.3;
  display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.var-name .var-ru{font-weight:600;color:#3A4A42}
/* Информационный кружок «i» стоит под номером переменной, в начале подписи */
.var-name .var-info{width:16px;height:16px;font-size:11px;font-style:italic;margin:0 5px 0 0;
  vertical-align:-3px;flex:0 0 auto}
.var-name .var-src{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.var-name code{font-size:11.5px;background:none;padding:0;color:#4A5C52}
.unused-vars{margin:14px 0 0;border-top:1px dashed var(--line);padding-top:10px}
.unused-vars summary{font-size:12.5px;color:#6B7C70;cursor:pointer}
.doc-note{font-size:11.5px;color:#6B7C70;margin-left:10px;max-width:520px;display:inline-block;vertical-align:middle}
.ex-tools{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0}
.kv-table tr:not(.kv-row-h):hover{background:#FAFCFB}
</style>"""

def _positional_order(html_text: str) -> dict:
    """Координаты переменных на странице: {имя: (top, left)} — первое вхождение.

    Нужно, чтобы список полей слева шёл в том же порядке, что и переменные
    в документе: сверху вниз, слева направо (учитываем вложенные absolute-блоки).
    """
    import re as _re
    from html.parser import HTMLParser as _HP

    class _P(_HP):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack = []
            self.found = {}
            self.seq = 0

        def handle_starttag(self, tag, attrs):
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
.var-line .var-rule-hint{display:block;font-size:11px;color:#6B7C70;margin-top:2px}
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
.var-src{display:block;font-size:11px;line-height:1.35;margin-top:2px}
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
                          color:#5B6B75;letter-spacing:.02em;pointer-events:none}
.pl-html .sheet-sep{position:absolute;left:0;right:0;height:0;
                    border-top:1px dashed #8E9BA4;pointer-events:none}
.pl-html .sheet-sep::before{content:'';position:absolute;left:0;right:0;top:-5px;height:10px;
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
.doc-verdict-float { position:absolute; left:14px; top:14px; z-index:20; display:flex; gap:4px; padding:3px;
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
.pl-html .zp-client-img { display:block; width:auto; max-width:none; height:auto; background:#fff;
  border:1px solid #D5DDE3; box-shadow:0 1px 3px rgba(16,32,44,.10); }}
.pl-html .zp-client-pdf { display:block; width:760px; height:70vh; border:0; background:#fff; }
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
  function esc(s){ return (window.CSS&&CSS.escape)?CSS.escape(s):String(s).replace(/[^a-zA-Z0-9_-]/g,''); }
  function clearHL(){
    document.querySelectorAll('tr.hl-row').forEach(function(x){x.classList.remove('hl-row');});
    document.querySelectorAll('.var-hl.hl-flash').forEach(function(x){x.classList.remove('hl-flash');});
  }
  /* связанные переменные: сумма цифрой и её написание прописью подсвечиваются вместе */
  function linkedTo(name){
    if(name==='balance_rub'||name==='balance_value'||name==='balance_words'||name==='balance_cents'){
      return ['balance_rub','balance_value','balance_words','balance_cents'].filter(function(x){ return x!==name; });
    }
    return [];
  }
  document.addEventListener('click', function(e){
    var t=e.target; if(!t||!t.closest) return;
    var inDocSpan = t.closest('.var-hl[data-var]');
    if(inDocSpan && t.closest('.zp-preview, #html-stage, [data-zoom-pan]')){
      var name = inDocSpan.getAttribute('data-var');
      /* дата формирования и период справки — одна связка: клик по любой из них подсвечивает строку №3 */
      var rowName = (name === 'period_from' || name === 'period_to') ? 'doc_date' : name;
      clearHL();
      /* Строку переменной ищем любым тегом: панель переменных — блоки, а не таблица
         (из-за поиска только по tr обратная подсветка не срабатывала). */
      var row = document.querySelector('[data-var-row="'+esc(rowName)+'"]');
      if(!row){
        var pre = String(rowName).split('_')[0];
        var all = document.querySelectorAll('[data-var-row]');
        for(var i=0;i<all.length;i++){
          if(all[i].getAttribute('data-var-row').split('_')[0]===pre){ row=all[i]; break; }
        }
      }
      if(row){
        row.classList.add('hl-row');
        /* Прокручиваем только панель переменных — каркас сайта и окно визора
           остаются на месте, строка встаёт напротив выбранного места. */
        (function(r){
          var sc=null, p=r.parentElement;
          while(p && p!==document.body){
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
            r.scrollIntoView({block:'nearest',behavior:'smooth'});
          }
        })(row);
        var inp = row.querySelector('input[data-var]');
        if(inp){ try{ inp.focus({preventScroll:true}); }catch(err){} }
        setTimeout(function(){ row.classList.remove('hl-row'); }, 3000);
      }
      inDocSpan.classList.add('hl-flash');
      setTimeout(function(){ inDocSpan.classList.remove('hl-flash'); }, 3000);
      /* сумма цифрой ↔ сумма прописью: подсвечиваем обе части */
      linkedTo(name).forEach(function(nm){
        document.querySelectorAll('.var-hl[data-var="'+esc(nm)+'"]').forEach(function(s2){
          s2.classList.add('hl-flash');
          setTimeout(function(){ s2.classList.remove('hl-flash'); }, 3000);
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
      if(n2 === 'doc_date'){ names.push('period_from', 'period_to'); }
      linkedTo(n2).forEach(function(x){ names.push(x); });
      var sp = [];
      names.forEach(function(nm){
        document.querySelectorAll('.var-hl[data-var="'+esc(nm)+'"]').forEach(function(s){
          sp.push(s);
          s.classList.add('hl-flash');
          setTimeout(function(){ s.classList.remove('hl-flash'); }, 3000);
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
  function esc(s){ return (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/[^a-zA-Z0-9_-]/g, ''); }
  /* номер карты: 16 цифр → 6 цифр + ****** + 4 цифры (в документ реальный номер не попадает) */
  function maskCard(v){
    v = (v || '').trim();
    if (!v || v.indexOf('*') >= 0) return v;
    var d = v.replace(/\D/g, '');
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
    var s=String(v||'').replace(/[.,]\s*\d{1,2}\s*$/,'');   /* копейки в пропись не входят */
    var n=Math.floor(Math.abs(Number(s.replace(/[^\d]/g,''))||0));
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
    var el=document.getElementById('tpl-months');
    var n=parseInt(el ? el.getAttribute('data-months') : '3', 10);
    return n===12 ? 12 : 3;
  }
  function fmtDate(d){
    return ('0'+d.getDate()).slice(-2)+'.'+('0'+(d.getMonth()+1)).slice(-2)+'.'+d.getFullYear();
  }
  function updPeriod(){
    var f=document.querySelector('input[data-var="doc_date"]');
    var v=f ? (f.value||'').trim() : '';
    var m=v.match(/^(\\d{1,2})\\.(\\d{1,2})\\.(\\d{4})$/);
    if(!m) return;
    var base=new Date(+m[3], (+m[2])-1, +m[1]);
    var from=new Date(+m[3], (+m[2])-1-tplMonths(), +m[1]);
    sync('period_from', fmtDate(from));
    sync('period_to', fmtDate(base));
  }
  function centsOf(v){
    var s=String(v||'').replace(/[^\d.,]/g,'');
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
  try{ var _nr=document.getElementById('num-rule');
    if(_nr){ var _r=JSON.parse(_nr.textContent||'{}'); for(var _k in _r){ if(_r[_k]) PATTERNS[_k]=_r[_k]; } } }catch(e){}
  function sync(name, val){
    var txt = (val || '').trim();
    document.querySelectorAll('.var-hl[data-var="' + esc(name) + '"]').forEach(function(sp){
      var ph = sp.getAttribute('data-ph') || '';
      /* форма иммиграции: пустое поле печатаем прочерком, имя переменной не показываем */
      if (!txt && sp.classList.contains('var-dash')) { sp.textContent = '-'; sp.classList.add('var-empty'); return; }
      sp.textContent = txt ? txt : ph;
      if (txt) sp.setAttribute('data-val', txt); else sp.removeAttribute('data-val');
      sp.classList.toggle('var-empty', !txt);
    });
  }
  function syncAll(){
    document.querySelectorAll('input[data-var]').forEach(function(i){
      sync(i.getAttribute('data-var'), i.value);
    });
    /* сумма прописью всегда соответствует показанному числу */
    var b = document.querySelector('input[data-var="balance_rub"], input[data-var="balance_value"]');
    if (b) { sync('balance_words', numToWordsEn(b.value)); sync('balance_cents', centsOf(b.value)); }
  }
  document.addEventListener('input', function(e){
    var i = e.target.closest ? e.target.closest('input[data-var]') : null;
    if (!i) return;
    var nm = i.getAttribute('data-var');
    if (nm === 'card_mask') {
      var masked = maskCard(i.value);
      if (masked !== i.value) i.value = masked;
    }
    sync(nm, i.value);
    /* сумма цифрами изменилась — сразу переписываем её прописью в документе */
    if (nm === 'balance_rub' || nm === 'balance_value') {
      sync('balance_words', numToWordsEn(i.value));
      sync('balance_cents', centsOf(i.value));
    }
    /* дата формирования изменилась — период справки считаем от неё */
    if (nm === 'doc_date') updPeriod();
  });
  document.addEventListener('change', function(e){
    var i = e.target.closest ? e.target.closest('select[data-var], textarea[data-var]') : null;
    if (i) sync(i.getAttribute('data-var'), i.value);
  });
  /* Enter в поле принимает значение в текущей ячейке — без перезагрузки страницы */
  document.addEventListener('keydown', function(e){
    var i = e.target.closest ? e.target.closest('input[data-var]') : null;
    if (!i || e.key !== 'Enter') return;
    e.preventDefault();
    var nm = i.getAttribute('data-var');
    if (nm === 'card_mask') { var m = maskCard(i.value); if (m !== i.value) i.value = m; }
    sync(nm, i.value);
    if (nm === 'balance_rub' || nm === 'balance_value') {
      sync('balance_words', numToWordsEn(i.value));
      sync('balance_cents', centsOf(i.value));
    }
    if (nm === 'doc_date') updPeriod();
    i.blur();
  });
  /* №3 — дата формирования: календарик возвращает текущую дату (админ может вписать свою) */
  document.addEventListener('click', function(e){
    var b = e.target.closest ? e.target.closest('.var-today') : null;
    if (!b) return;
    e.preventDefault();
    var nm = b.getAttribute('data-var') || 'doc_date';
    var f = document.querySelector('input[data-var="' + esc(nm) + '"]');
    if (!f) return;
    var d = new Date();
    var pad = function(x){ return ('0' + x).slice(-2); };
    f.value = pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + '.' + d.getFullYear();
    sync(nm, f.value);
    f.dispatchEvent(new Event('input', {bubbles: true}));
  });
  /* Сгенерировали кубиком или выбрали из списка — строка становится жёлтой:
     значение не вытащено из документа, значит требует проверки администратором. */
  function markSynth(nm){
    if (!nm) return;
    var tr = document.querySelector('tr[data-var-row="' + esc(nm) + '"]');
    if (!tr) return;
    tr.className = 'var-kind-synth';
    var s = tr.querySelector('.var-src');
    if (s) { s.className = 'var-src var-src-synth'; s.textContent = '🟡 сгенерировано системой — проверьте'; }
  }
  document.addEventListener('change', function(e){
    var f = e.target;
    if (f && f.matches && f.matches('input[data-var]')) markSynth(f.getAttribute('data-var'));
  });
  document.addEventListener('click', function(e){
    var b = e.target.closest ? e.target.closest('.var-dice') : null;
    if (b) {
      e.preventDefault();
      var nm = b.getAttribute('data-var'), p = PATTERNS[nm];
      markSynth(nm);
      var f = nm ? document.querySelector('input[data-var="' + esc(nm) + '"]') : null;
      if (f && (nm === 'balance_rub' || nm === 'balance_value')) {
        /* №7 — сумма остатка: новое число в диапазоне своего типа справки (3 мес. или 12 мес.), с копейками */
        var lo = parseInt(b.getAttribute('data-min') || '190000', 10);
        var hi = parseInt(b.getAttribute('data-max') || '800000', 10);
        var amount = lo + Math.floor(Math.random() * (hi - lo + 1));
        var kop = ('0' + Math.floor(Math.random() * 100)).slice(-2);
        var fmt = b.getAttribute('data-fmt') || 'space';
        /* в справках Сбера разряды идут без пробелов (в 3-мес. подлиннике 17621.29) */
        f.value = (fmt === 'dot') ? String(amount) + '.' + kop
                : (fmt === 'plain') ? String(amount) + ',' + kop
                : String(amount).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ',' + kop;
        sync(nm, f.value);
        f.dispatchEvent(new Event('input', {bubbles:true}));
        return;
      }
      if (f && nm === 'card_mask') {
        /* номер карты: и БИН, и остальные цифры берём новые — но только из набора своего банка */
        var bins = (b.getAttribute('data-bins') || '220070').split(',').map(function(x){ return x.trim(); });
        var bin = bins[Math.floor(Math.random() * bins.length)];
        f.value = maskCard(bin + genByPattern('dddddddddd'));
        sync(nm, f.value);
        f.dispatchEvent(new Event('input', {bubbles:true}));
        return;
      }
      if (f && p) { f.value = genByPattern(p); sync(nm, f.value); f.dispatchEvent(new Event('input', {bubbles:true})); }
      return;
    }
    var t = e.target.closest ? e.target.closest('#ex-fill, #ex-clear') : null;
    if (t) setTimeout(syncAll, 30);
  });
  document.addEventListener('DOMContentLoaded', function(){ setTimeout(function(){ syncAll(); if(window.updPeriod) window.updPeriod(); }, 60); });
  window.__syncVarToDoc = sync;
  /* Индикатор заполненности: сколько полей ещё пусто (служебные и необязательные не считаем).
     Когда всё заполнено — значок становится зелёным, в окне PDF плашка исчезает. */
  var OPTIONAL_VARS = {period_from:1, period_to:1, balance_words:1, balance_cents:1,
                       account_no:1, contract_date:1, contract_no:1};
  function emptyVars(){
    var out = [];
    document.querySelectorAll('input[data-var]').forEach(function(i){
      var nm = i.getAttribute('data-var');
      if(OPTIONAL_VARS[nm]) return;
      if(!String(i.value || '').trim()) out.push(nm);
    });
    return out;
  }
  function refreshFillFlag(){
    var miss = emptyVars();
    /* Счётчик в заголовке панели переменных: сколько всего и сколько заполнено.
       Красный, если есть пустые; зелёный, когда заполнено всё. */
    var cnt = document.getElementById('vars-count');
    if(cnt){
      var inputs = document.querySelectorAll('.tpl-panel.is-vars input[data-var]');
      var total = inputs.length, filled = total - miss.length;
      cnt.classList.toggle('is-ok', miss.length === 0);
      cnt.classList.toggle('is-bad', miss.length > 0);
      cnt.textContent = '(всего ' + filled + '/' + total + (miss.length === 0 ? ' ок' : '') + ')';
      cnt.title = miss.length === 0 ? 'Заполнены все переменные'
                                    : ('Пустые: ' + miss.join(', '));
    }
    var flag = document.getElementById('fill-flag');
    if(flag){
      flag.classList.toggle('is-ok', miss.length === 0);
      flag.textContent = miss.length === 0 ? '✅ все поля заполнены' : ('⚠️ не заполнено полей: ' + miss.length);
      flag.title = miss.length === 0 ? 'Все поля заполнены — можно формировать документ'
                                     : ('Пустые поля: ' + miss.join(', '));
    }
    var warn = document.getElementById('pdf-warn');
    if(warn){
      warn.hidden = miss.length === 0;
      if(miss.length) warn.textContent = '⚠️ Не все поля заполнены: ' + miss.join(', ');
    }
  }
  window.__refreshFillFlag = refreshFillFlag;
  document.addEventListener('input', refreshFillFlag);
  document.addEventListener('change', refreshFillFlag);
  setTimeout(refreshFillFlag, 150);
  /* полная очистка: поля ввода + все переменные в документе (включая период) */
  function clearValues(){
    document.querySelectorAll('.kv-table input[data-var], .kv-table select[data-var], .kv-table textarea[data-var]').forEach(function(i){
      i.value='';
    });
    /* чистим ТОЛЬКО переменные в самом документе: кнопки (галочка, кубик, инфо) тоже помечены
       data-var — раньше у них стиралось содержимое, и значки пропадали безвозвратно */
    var st = document.querySelector('#html-stage') || document.querySelector('.html-stage');
    if (!st) return;
    st.querySelectorAll('[data-var]').forEach(function(sp){
      if (/^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(sp.tagName)) return;
      /* пустая переменная остаётся видимой: показываем её имя серым, чтобы в документе
         было понятно, где она стояла (никаких {{ имя }} из шаблона) */
      sp.textContent = sp.getAttribute('data-var');
      sp.removeAttribute('data-val');
      sp.classList.add('var-empty');
    });
  }
  /* функции нужны другим блокам страницы: кнопки «Очистить поля» и «Из примера» */
  window.sync = sync; window.updPeriod = updPeriod; window.clearValues = clearValues;
})();
</script>"""


_LANG_JS = """<script>
(function(){
  function stage(){ return document.querySelector('.html-stage') || document.querySelector('.doc-html-stage'); }
  function pvals(){
    var arr=[];
    document.querySelectorAll('input[data-var]').forEach(function(i){
      var v=(i.value||'').trim(); if(v) arr.push(v); });
    return arr;
  }
  function nodes(){
    var st=stage(); if(!st) return [];
    var pv = pvals();            // значения переменных считаем ОДИН раз (иначе падало: pvals.indexOf)
    var sheets=st.querySelectorAll('.sheet');
    var roots = sheets.length ? sheets : [st];
    var out=[];
    roots.forEach(function(root){
      var w=document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
      while(w.nextNode()){
        var n=w.currentNode, t=n.nodeValue;
        if(!t || !t.trim()) continue;
        var par=n.parentNode, tag=par&&par.nodeName?par.nodeName.toLowerCase():'';
        if(tag==='style'||tag==='script'||tag==='title') continue;   // НЕ переводим CSS/JS
        if(/\{\{/.test(t)) continue;                                 // не трогаем {{ переменные }}
        /* Переводим только осмысленный текст — где есть минимум две буквы подряд.
           Пунктиры, числа, «: ……………» и прочая служебная разметка остаются как есть,
           иначе поля «плыли» и вёрстка разъезжалась относительно оригинала. */
        if(!/[A-Za-zА-Яа-яЁё]{2}/.test(t)) continue;
        if(t.trim().length < 2) continue;
        if(pv.indexOf(t.trim()) >= 0){                                 // значение переменной
          /* Кусочки (описание профессии, обязанности, «о себе») переводим:
             у них в памяти сервера есть готовая русская пара. Данные клиента
             (ФИО, паспорт, даты, гражданство) не переводим. */
          var hl=par&&par.closest?par.closest('.var-hl[data-var]'):null;
          var vn=hl?(hl.getAttribute('data-var')||''):'';
          /* Кроме кусочков резюме переводим «смысловые» значения договора о работе:
             должность и перечень обязанностей — администратор читает их по-русски.
             Реквизиты, ФИО, паспорт, даты и суммы остаются как в документе. */
          if(!/^(cv_(job\d+_(bullets|title)|summary|profession|skills|position|education)|position_title|services_list)$/.test(vn)) continue;
        }
        out.push(n);
      }
    });
    return out;
  }
  var saved=null, busy=false, busyTmr=null;
  /* Шаблон текущего документа: в заявке URL — /applications/<id>/review, поэтому
     берём id из кнопки PDF, а в конструкторе — из адреса страницы. */
  function docTpl(){
    var b=document.getElementById('tpl-pdf-open');
    var t=(b&&b.getAttribute('data-template'))||'';
    if(!t){ t=(location.pathname.match(/\/templates\/(\d+)/)||[])[1]||''; }
    return t;
  }
  var LS='woTrans:'+(docTpl()||location.pathname);   // локальный кэш переводов этого документа
  /* Подстановка перевода в текстовый узел: перенос строки из ответа модели заменяем пробелом
     (иначе фраза разваливалась на несколько строк и вёрстка ехала), а пробелы-отступы
     вокруг исходного текста сохраняем. */
  function put(n, tr){
    var raw=n.nodeValue, k=raw.trim();
    var clean=String(tr).replace(/\\s*\\n+\\s*/g,' ').replace(/\\s{2,}/g,' ').trim();
    var pos=raw.indexOf(k);
    n.nodeValue = (pos>=0 ? raw.slice(0,pos)+clean+raw.slice(pos+k.length) : clean);
  }
  function note(txt){ var el=document.getElementById('ls-note'); if(el) el.textContent=txt||''; }
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
      document.querySelectorAll('[data-base-fs]').forEach(function(el){
        el.style.fontSize=el.dataset.baseFs; delete el.dataset.baseFs;
      });
    }catch(e){}
  }
  /* Галочка и крестик относятся только к нашим документам: при просмотре файлов
     клиента рамку с ними прячем (заявка #72). */
  function verdictBox(on){ var f=document.querySelector('.doc-verdict-float'); if(f) f.hidden=!on; }
  /* Защита от «кнопка не работает»: busy снимается сам через 5 секунд, если запрос
     не вернулся (раньше флаг залипал, и все нажатия молча проглатывались). */
  function setBusy(v){
    busy=v; if(busyTmr){ clearTimeout(busyTmr); busyTmr=null; }
    if(v){ busyTmr=setTimeout(function(){ busy=false; note('перевод не ответил — попробуйте ещё раз'); }, 5000); }
  }
  function setBtn(lang){
    document.querySelectorAll('#lang-switch .ls-btn').forEach(function(b){
      b.classList.toggle('is-on', b.dataset.lang===lang); });
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
    var url = tpl ? ('/templates/' + tpl + '/translate')
                  : (location.pathname.replace(/\/+$/,'') + '/translate');
    function ask(cacheOnly, part){
      return fetch(url, {
        method:'POST', headers:{'Content-Type':'application/json','X-Requested-With':'fetch'},
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
      var url = tpl ? ('/templates/' + tpl + '/translate')
                    : (location.pathname.replace(/\/+$/,'') + '/translate');
      fetch(url, {method:'POST', headers:{'Content-Type':'application/json','X-Requested-With':'fetch'},
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
  document.addEventListener('click', function(e){
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
    if(!box){ box = document.createElement('div'); box.className = 'var-full'; holder.appendChild(box); }
    return box;
  }
  function isLong(i){
    var v = i.value || '';
    return v.length > 48 || i.scrollWidth > i.clientWidth + 2;
  }
  function show(i){
    if(!i || !i.dataset || i.dataset.var===undefined) return;
    var box = hbox(i);
    box.textContent = i.value || '';
    box.classList.toggle('is-on', isLong(i) && !!i.value);
  }
  function hide(i){
    if(!i || !i.dataset || i.dataset.var===undefined) return;
    var box = hbox(i);
    box.classList.remove('is-on');
  }
  document.addEventListener('focusin', function(e){ show(e.target); }, true);
  document.addEventListener('click', function(e){
    var b = e.target.closest && e.target.closest('.var-full');
    if(b){ b.classList.remove('is-on'); return; }
    if(e.target.matches && e.target.matches('input[data-var],textarea[data-var]')) show(e.target);
  }, true);
  document.addEventListener('input', function(e){
    var i = e.target;
    if(i && i.dataset && i.dataset.var!==undefined){
      if(isLong(i) && document.activeElement === i) show(i); else hide(i);
    }
  }, true);
  document.addEventListener('focusout', function(e){
    var i = e.target;
    if(!i || !i.dataset || i.dataset.var===undefined) return;
    setTimeout(function(){ if(document.activeElement !== i) hide(i); }, 160);
  }, true);
})();
/* Подстановка значений из реального примера */
(function(){
  function fill(){
    var el=document.getElementById('ex-data'); if(!el) return;
    var map={}; try{ map=JSON.parse(el.textContent||'{}'); }catch(e){ return; }
    var n=0;
    /* ФИО всегда берём из данных клиента: в оригинальных примерах отчества нет,
       поэтому примером их не перетираем */
    var SKIP={client_name:1,full_name:1,full_name_latin:1,cv_name:1,employee_name:1,
              employee_full_name:1,employee_full_name_latin:1,surname:1,name:1,patronymic:1};
    Object.keys(map).forEach(function(k){
      if(SKIP[k]) return;
      var inp=document.querySelector('input[data-var="'+k+'"]');
      if(inp){ inp.value=map[k]; inp.dispatchEvent(new Event('input',{bubbles:true})); n++; }
      /* переменные без своего поля (период справки) ставим прямо в документ — как в примере */
      else if(window.sync){ window.sync(k, map[k]); }
    });
    /* период не берём из примера: он всегда считается от даты — 3 или 12 месяцев назад */
    if(window.updPeriod) window.updPeriod();
  }
  function clearAll(){
    document.querySelectorAll('.kv-table input[data-var], .kv-table select[data-var], .kv-table textarea[data-var]').forEach(function(i){
      i.value=''; i.dispatchEvent(new Event('input',{bubbles:true})); });
    /* все переменные в документе сбрасываем в {{ имя }} — включая дату и период */
    if (window.clearValues) window.clearValues();
    /* повторяем после всех обработчиков — иначе период успевает вернуться */
    if (window.clearValues) { setTimeout(window.clearValues, 60); setTimeout(window.clearValues, 300); }
  }
  document.addEventListener('click', function(e){
    var t=e.target; if(!t.closest) return;
    if(t.closest('#ex-fill')){ e.preventDefault(); fill(); }
    else if(t.closest('#ex-clear')){ e.preventDefault(); clearAll(); }
  });

  /* Кнопок «Подставить значения из примера» и «Очистить поля» больше нет: значения
     из примера подставляются сразу при открытии документа, по стандарту. В режиме
     заявки (data-autofill="0") данные клиента не трогаем. */
  (function(){
    var box=document.querySelector('.ex-tools[data-autofill="1"]');
    if(!box) return;
    function run(){ try{ fill(); }catch(err){} }
    window.exAutofill=run;
    if(document.readyState==='loading'){
      document.addEventListener('DOMContentLoaded', function(){ setTimeout(run, 150); });
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
  function st(){ return document.getElementById('html-stage'); }
  function mark(b){ document.querySelectorAll('.js-docmode').forEach(function(x){ x.classList.toggle('is-on', x===b); }); }
  function refit(){ if(window.zpScan) setTimeout(window.zpScan, 80); }
  /* Переключение вкладок не должно накапливать масштаб: снимаем трансформацию листа
     до пересчёта, иначе каждый переход уменьшал документ (76→72→68…). */
  function resetScale(){ var s=st(); if(!s) return;
    s.style.transform=''; s.style.transformOrigin=''; s.style.width=''; }
  /* Переключили документ — сохранённый HTML-шаблон старого документа больше не годится:
     без сброса вкладка «HTML шаблон» возвращала предыдущий документ. */
  window.zpDocTabsReset=function(mode){
    orig=null;
    var sel=(mode==='orig') ? '.js-docmode[data-pdfview]' : '.js-docmode[data-mode="html"]';
    var b=document.querySelector(sel) || document.querySelector('.js-docmode[data-mode="html"]');
    if(b) mark(b);
  };
  /* Переключение вкладок НЕ перезагружает страницу и не трогает переменные:
     меняется только содержимое окна визора. Лист не схлопывается (сайт стоит статично) —
     старый документ мягко гаснет, новый проявляется. Позиция и высота окна сохраняются. */
  /* Высоту окна держим неизменной на время подмены, а позицию сайта — возвращаем. */
  function holdWindow(){
    var host=document.querySelector('.pl-html .zp-host'); if(!host) return function(){};
    var h=Math.round(host.getBoundingClientRect().height), prev=host.style.minHeight;
    if(h>120) host.style.minHeight=h+'px';
    return function(){ host.style.minHeight=prev||''; };
  }
  /* Возврат позиции — аккуратно: если сдвиг меньше 6 px, не трогаем (иначе виден скачок
     всей страницы, который читается как «экран схлопнулся и раскрылся»). */
  function restoreScroll(y, hostTop){
    if(hostTop!=null){
      var host=document.querySelector('.pl-html .zp-host');
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
    var pl=document.querySelector('.pl-html');
    var host=document.querySelector('.pl-html .zp-host');
    var keepY=(window.scrollY||window.pageYOffset||0);
    var keepTop=host?host.getBoundingClientRect().top:null;
    var keepH=host?Math.round(host.getBoundingClientRect().height):0;
    var release=holdWindow();
    window.__zpHoldWindow=true;
    /* Высота окна замораживается: пока смотрим другой вариант того же документа, окно
       не должно менять размер — иначе дёргается вся страница (Андрей, 04.10.2026). */
    if(keepH>120){ window.__zpFreezeH=keepH; host.style.height=keepH+'px'; }
    if(pl) pl.classList.add(soft?'is-fading':'is-collapsing','is-loading');
    setTimeout(function(){
      try{ work(); }catch(err){}
      if(pl) pl.classList.remove('is-collapsing');
      if(pl) pl.classList.remove('is-fading');
      setTimeout(function(){
        if(pl) pl.classList.remove('is-loading'); release();
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
    var pl0=document.querySelector('.pl-html'), host0=pl0?pl0.querySelector('.zp-host'):null;
    /* Размеры окна визора и полос при открытии файла клиента не меняем:
       окно было 900 px, а после PDF клиента схлопывалось до 180 px и «прыгала» вся раскладка. */
    var keepH = window.__zpFreezeH || (host0?Math.round(host0.getBoundingClientRect().height):0);
    var keepW = host0?Math.round(host0.getBoundingClientRect().width):0;
    var __vb=document.querySelector('.doc-verdict-float'); if(__vb) __vb.hidden=true;   /* файл клиента — галочка и крестик здесь не нужны */
    foldAndSwap(null, function(){
      if(orig===null) orig=s.innerHTML;     /* чтобы «HTML шаблон» вернул документ */
      resetScale();
      if(['png','jpg','jpeg','webp','gif','bmp'].indexOf(ext)>=0){
        s.innerHTML='<img class="zp-client-img" src="'+url+'" alt="">';
        var im=s.querySelector('img');
        if(im){ im.addEventListener('load', function(){ softRefit(); window.dispatchEvent(new Event('resize')); }); }
      } else {
        var w=keepW?keepW-28:760;
        var h=keepH?keepH-28:Math.round(window.innerHeight*0.70);
        s.innerHTML='<iframe class="zp-client-pdf" style="width:'+w+'px;height:'+h+'px" src="'+url+'#view=FitH"></iframe>';
      }
      softRefit();
    }, true);
    if(keepH>120){ window.__zpFreezeH=keepH; if(host0) host0.style.height=keepH+'px'; }
    if(mini){
      document.querySelectorAll('.tpl-mini').forEach(function(x){ x.classList.remove('is-on'); });
      mini.classList.add('is-on');
    }
  }
  /* Клик по миниатюре клиента — показываем её в окне визора (Ctrl+клик — новая вкладка) */
  document.addEventListener('click', function(e){
    var a=e.target.closest ? e.target.closest('.tpl-mini[data-client-file]') : null;
    if(!a) return;
    if(e.ctrlKey||e.metaKey||e.shiftKey) return;
    e.preventDefault();
    loadClientFile(a.getAttribute('data-url'), a.getAttribute('data-name'), a);
  });
  function showHtml(btn){
    var __vb=document.querySelector('.doc-verdict-float'); if(__vb) __vb.hidden=false;   /* наш документ — согласование доступно */
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
      h = String(h).replace(/<style[\s\S]*?<\/style>/gi,'').replace(/<script[\s\S]*?<\/script>/gi,'');
      var box = document.createElement('div'); box.innerHTML = h;
      var inner = box.querySelector('.pdf-page-list, .pdf-pages, .paper-body, #pages') || box;
      s.innerHTML = inner.innerHTML; softRefit();
    }).catch(function(){ s.innerHTML='<div style="padding:24px;color:#B91C1C">Не удалось загрузить PDF</div>'; softRefit(); });
  }
  function showPdf(url, btn){ foldAndSwap(btn, function(){ loadPdf(url, btn); }, true); }
  /* Смена документа из миниатюры: вариант просмотра сохраняется. Если была открыта вкладка
     «Оригинальный пример» — грузим оригинал нового документа, а не перескакиваем на HTML. */
  window.zpDocLoadPdf=function(){
    var b=document.querySelector('.js-docmode[data-pdfview]');
    if(b) loadPdf(b.dataset.pdfview, b);
  };
  document.addEventListener('click', function(e){
    var t=e.target; if(!t.closest) return;
    var btn=t.closest('.js-docmode'); if(!btn) return;
    e.preventDefault();
    if(btn.classList.contains('is-on')) return;
    /* повторный клик во время переключения игнорируем */
    if(document.querySelector('.pl-html.is-loading')) return;
    if(btn.dataset.pdfview) showPdf(btn.dataset.pdfview, btn); else showHtml(btn);
  });
})();

/* === Мягкое переключение документов: без перезагрузки страницы ===================
   Меняются только окно просмотра и перечень переменных; шапка, тулбар, миниатюры и
   разметка сайта остаются на месте. Панель переменных перед подменой сворачивается
   вверх и разворачивается уже с новыми значениями. */
(function(){
  var stage=document.getElementById('html-stage');
  var varsPanel=document.querySelector('.tpl-panel.is-vars');
  if(!stage||!varsPanel) return;

  /* Скрипты внутри подменённого куска браузер сам не запускает — запускаем повторно,
     иначе кнопки переменных в новой панели не работают. */
  function runScripts(root){
    root.querySelectorAll('script').forEach(function(old){
      var s=document.createElement('script');
      if(old.src){ s.src=old.src; } else { s.textContent=old.textContent; }
      old.parentNode.replaceChild(s, old);
    });
  }

  var busy=false;
  function swap(url, mini){
    if(busy) return;
    var pl=document.querySelector('.pl-html');
    window.__zpFreezeH=null;   /* новый документ — высота окна считается заново */
    window.__zpUserScrolled=false;   /* и лист снова центрируем */
    busy=true;
    /* лист сворачивается в точку, в центре крутится колёсико, переменные уезжают вверх */
    if(pl) pl.classList.add('is-loading','is-collapsing');
    varsPanel.classList.add('is-swapping');
    var foldDone=new Promise(function(res){ setTimeout(res, 620); });
    Promise.all([fetch(url,{credentials:'same-origin'}).then(function(r){ return r.text(); }), foldDone])
      .then(function(res){ return res[0]; })
      .then(function(h){
      var doc=new DOMParser().parseFromString(h,'text/html');
      var nStage=doc.getElementById('html-stage');
      var nVars=doc.querySelector('.tpl-panel.is-vars');
      var nTabs=doc.getElementById('doc-tabs');
      var tabs=document.getElementById('doc-tabs');
      if(nStage) stage.innerHTML=nStage.innerHTML;
      var __vb2=document.querySelector('.doc-verdict-float'); if(__vb2) __vb2.hidden=false;   /* открыли наш документ */
      if(nVars) varsPanel.innerHTML=nVars.innerHTML;
      if(nTabs&&tabs) tabs.innerHTML=nTabs.innerHTML;
      var nT=doc.querySelector('.tpl-title'), oT=document.querySelector('.tpl-title');
      if(nT&&oT) oT.textContent=nT.textContent;
      var nMeta=doc.querySelector('.tpl-meta'), oMeta=document.querySelector('.tpl-meta');
      if(nMeta&&oMeta) oMeta.innerHTML=nMeta.innerHTML;
      document.querySelectorAll('.tpl-mini').forEach(function(x){ x.classList.remove('is-on'); });
      if(mini) mini.classList.add('is-on');
      var tt=document.getElementById('pv-title');
      if(tt) tt.textContent='Окно просмотра (визор)';
      /* хлебные крошки: последняя крошка — название документа */
      var crumb=null;
      document.querySelectorAll('a').forEach(function(a){ if(a.textContent.trim()==='Конструктор PDF') crumb=a; });
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
      try{ history.pushState({},'',url); }catch(e){}
      /* разворот по шагам: сначала лист из точки, затем переменные сверху вниз */
      var resetAt=pl?pl.querySelector('.zp-preview'):null;
      if(resetAt){ resetAt.scrollTop=0; }
      setTimeout(function(){ if(pl) pl.classList.remove('is-collapsing'); }, 280);
      setTimeout(function(){ varsPanel.classList.remove('is-swapping'); }, 620);
      setTimeout(function(){ if(pl) pl.classList.remove('is-loading'); busy=false; }, 1350);
    }).catch(function(){ if(pl){ pl.classList.remove('is-loading','is-collapsing'); }
                         varsPanel.classList.remove('is-swapping'); busy=false; });
  }

  document.addEventListener('click', function(e){
    var a=e.target.closest('.tpl-mini'); if(!a) return;
    if(a.classList.contains('is-on')){ e.preventDefault(); return; }
    e.preventDefault();
    swap(a.getAttribute('href'), a);
  });
  window.addEventListener('popstate', function(){ location.reload(); });
})();
</script>"""


@bp.route("/templates/<int:template_id>/translate", methods=["POST"])
def translate_doc(template_id: int):
    """Перевод бланка документа: вся работа — в services/translate.py."""
    raw = request.get_json(silent=True) or {}
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

@bp.route("/templates/<int:template_id>/var/<name>/chat", methods=["GET", "POST"])
def var_chat(template_id: int, name: str):
    """Диалог с ИИ-агентом по правилу формирования переменной."""
    if request.method == "GET":
        rows = db.q(
            "SELECT role, content FROM variable_chat WHERE template_id=? AND var_name=? "
            "ORDER BY id DESC LIMIT 20", (template_id, name)) or []
        msgs = [{"role": r["role"], "content": r["content"]} for r in rows][::-1]
        return jsonify({"ok": True, "messages": msgs})

    raw = request.get_json(silent=True) or request.form or {}
    msg = str(raw.get("message", "") or "").strip()
    if not msg:
        return jsonify({"ok": False, "error": "пустое сообщение"}), 400
    cur_rule = str(raw.get("rule", "") or "").strip()

    tpl = db.q1("SELECT title, doc_index FROM templates WHERE id=?", (template_id,)) or {}
    doc_label = "Документ №%s «%s»" % (tpl.get("doc_index") or template_id, tpl.get("title") or "")

    prev = db.q(
        "SELECT role, content FROM variable_chat WHERE template_id=? AND var_name=? "
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
        db.exec_sql("INSERT INTO variable_chat(template_id,var_name,role,content) VALUES(?,?,?,?)",
                    (template_id, name, "user", msg))
        db.exec_sql("INSERT INTO variable_chat(template_id,var_name,role,content) VALUES(?,?,?,?)",
                    (template_id, name, "assistant", reply))
    except Exception:
        pass
    return jsonify({"ok": True, "reply": reply})


@bp.route("/templates/<int:template_id>/var/<name>/rule", methods=["POST"])
def var_rule(template_id: int, name: str):
    """Сохранить инструкцию формирования переменной (rule_note)."""
    raw = request.get_json(silent=True) or request.form or {}
    txt = str(raw.get("rule", "") or "").strip()
    try:
        db.exec_sql(
            "UPDATE template_variables SET rule_note=? WHERE template_id=? AND name=?",
            (txt, template_id, name),
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "rule": txt})


@bp.route("/templates/<int:template_id>/var/<name>/approve", methods=["POST"])
def var_approve(template_id: int, name: str):
    """Статус согласования переменной: ✅ согласовано / ! требует проверки."""
    raw = request.get_json(silent=True) or request.form or {}
    val = 1 if str(raw.get("approved", "")).lower() in ("1", "true", "yes") else 0
    try:
        db.exec_sql(
            "UPDATE template_variables SET approved=? WHERE template_id=? AND name=?",
            (val, template_id, name),
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    try:
        db.log_event("template", template_id,
                     "var_approved" if val else "var_unapproved",
                     actor=current_user()["login"])
    except Exception:
        pass
    return jsonify({"ok": True, "approved": val})


@bp.route("/templates/<int:template_id>/toggle-reviewed", methods=["POST"])
@login_required
def toggle_reviewed(template_id: int):
    from flask import jsonify
    cur = db.q1("SELECT reviewed FROM templates WHERE id=?", (template_id,))
    if not cur:
        return jsonify({"ok": False, "error": "not found"}), 404
    new_val = 0 if cur.get("reviewed") else 1
    db.exec_sql("UPDATE templates SET reviewed=? WHERE id=?", (new_val, template_id))
    try:
        db.log_event("template", template_id,
                     "reviewed_on" if new_val else "reviewed_off",
                     actor=current_user()["login"])
    except Exception:
        pass
    return jsonify({"ok": True, "reviewed": bool(new_val)})


def _group_info(title: str) -> dict:
    """Описание группы документов на русском — для кнопки «ℹ️» у группы."""
    t = (title or "").lower()
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
            "kind": "Три формата одного слота: короткий (1 стр. — простой опыт), расширенный (2 стр. — развёрнутый summary и обязанности, ставится по умолчанию), «формат Сиваева» (1 стр. — для топ-позиций).",
            "how": "Структура: шапка с именем и должностью → личные данные → summary → опыт работы с датами и обязанностями → образование → навыки → языки. Всё, что относится к человеку, — переменная, статического текста быть не должно.",
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
            "why": "D12 (Pra-Investasi) — многократная виза на 1–2 года: спонсор просит выдать её клиенту и ручается за его пребывание.",
            "kind": "Лист 1 — ходатайство, лист 2 — заявление гаранта; данные клиента стоят на втором листе, проверять оба.",
            "how": "Обязателен номер письма вида NN/PTAPB-SP/ДД.ММ.ГГГГ, место и дата подписания по-индонезийски. Один документ вместо двух одинаковых — раньше была ошибка с дублем на 4 страницы.",
            "where": "D12 (в комплекте вместе с двумя банковскими справками и резюме).",
        }
    if "e-02" in t or "e02" in t or "statement letter" in t:
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
            "kind": "Тема письма меняется вместе с переходом: «Permohonan Bridging Visa 60 Hari» или «Konversi Bridging Visa menjadi KITAS E33G Remote Worker».",
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


def _group_modal(slug: str, title: str, doc_list, info: dict) -> str:
    """Всплывающее описание группы документов: что это, кому нужно, как делается."""
    rows = "".join(
        f'<div class="pi-section"><div class="pi-label">{lbl}</div>'
        f'<div class="pi-text">{info.get(key) or "—"}</div></div>'
        for key, lbl in (("about", "Что это за документы"), ("who", "Кто оформляет и куда идёт"),
                         ("why", "Для чего нужно"), ("kind", "Какие бывают"),
                         ("how", "Как делается"), ("where", "В каких продуктах")))
    names = "".join(f'<li>{t}</li>' for t in doc_list)
    hero = (f'<div class="pi-hero"><div class="pi-title">📚 {title}</div>'
            f'<div class="pi-sub">Документов в группе: {len(doc_list)}</div></div>')
    lst = (f'<div class="pi-section"><div class="pi-label">Документы группы</div>'
           f'<div class="pi-text"><ul style="margin:0;padding-left:18px">{names}</ul></div></div>')
    return modal(f"m_grp_{slug}", "О документах группы", hero + rows + lst)


def _group_slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (title or "").lower()).strip("_")[:44] or "group"


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
            elif part.startswith("html ") or part.startswith("body "):
                out.append(scope + " " + part.split(" ", 1)[1])
            else:
                out.append(part if part.startswith(scope) else scope + " " + part)
        return ", ".join(out) if out else scope

    res, i = [], 0
    while True:
        m = re.search(r"\{", css[i:])
        if not m:
            break
        open_at = i + m.start()
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
        if sel.startswith("@media"):
            res.append(sel + " {" + _scope_css(body, scope) + "}")
        elif sel.startswith("@"):
            res.append(sel + " {" + body + "}")
        else:
            res.append(scope_sel(sel) + " {" + body + "}")
        i = j + 1
    return "".join(res)


@bp.route("/templates/gdrive/<int:client_id>/file")
@login_required
def gdrive_example_file(client_id: int):
    """Показать реальный документ клиента из кэша Google Диска (пример в конструкторе).

    Заказчик обыгрывает сценарий на шаблонных данных, но вкладка «Клиент» должна содержать
    настоящие документы, с которых система берёт значения: паспорт, фото, справку банка.
    """
    from flask import send_file
    name = (request.args.get("name") or "").strip()
    base = (BASE_DIR / "data" / "gdrive_cache" / ("client_%d" % client_id)).resolve()
    fp = (base / name).resolve()
    if not name or not str(fp).startswith(str(base)) or not fp.is_file():
        abort(404)
    return send_file(str(fp))


@bp.route("/templates/gdrive/<int:client_id>/thumb")
@login_required
def gdrive_example_thumb(client_id: int):
    """Миниатюра реального документа клиента: картинка как есть, PDF — первая страница."""
    from flask import Response, send_file
    name = (request.args.get("name") or "").strip()
    base = (BASE_DIR / "data" / "gdrive_cache" / ("client_%d" % client_id)).resolve()
    fp = (base / name).resolve()
    if not name or not str(fp).startswith(str(base)) or not fp.is_file():
        return Response("", status=404)
    ext = fp.suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        resp = send_file(str(fp), conditional=True)
        resp.headers["Cache-Control"] = "private, max-age=600"
        return resp
    if ext != ".pdf":
        return Response("", status=404)
    cache_dir = BASE_DIR / "data" / "previews"
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / ("gd_%d_%s.webp" % (client_id, hashlib.md5(name.encode()).hexdigest()[:10]))
    if not out.exists():
        try:
            import pymupdf
            doc = pymupdf.open(str(fp))
            pix = doc[0].get_pixmap(dpi=90)
            pix.save(str(out))
            doc.close()
        except Exception:  # noqa: BLE001
            return Response("", status=404)
    resp = send_file(str(out), mimetype="image/webp", conditional=True)
    resp.headers["Cache-Control"] = "private, max-age=600"
    return resp


@bp.route("/templates/<int:template_id>/thumb")
@login_required
def template_thumb(template_id: int):
    """Миниатюра документа-шаблона для вертикальной полоски в конструкторе."""
    from flask import Response, send_file
    from services import previews
    t = db.q1("SELECT id, code FROM templates WHERE id=?", (template_id,)) or {}
    if not t:
        return Response("", status=404)
    # ?app=<id> — миниатюра того же документа, но собранного на реальных данных клиента
    # заявки: в конструкторе продукта наши документы должны показывать те же данные,
    # что и клиентские файлы (требование Андрея, 06.10.2026).
    _app = request.args.get("app", type=int)
    out = None
    if _app:
        try:
            out = previews.tpl_thumb_client(template_id, t.get("code") or "", _app, 170)
        except Exception:  # noqa: BLE001
            out = None
    if not out:
        out = previews.tpl_thumb(template_id, t.get("code") or "", 170)
    if not out:
        return Response("", status=404)
    resp = send_file(str(out), mimetype="image/webp", conditional=True)
    # Миниатюра меняется вместе с примерами переменных — браузер не должен держать старую
    # (у Андрея в кэше сутки висел пустой бланк после перехода на заполненные миниатюры).
    resp.headers["Cache-Control"] = "private, no-cache, max-age=0"
    return resp


@bp.route("/templates")
@login_required
def page():
    products = db.q("""SELECT p.*, COUNT(pd.id) doc_count
                       FROM products p LEFT JOIN product_documents pd ON pd.product_id=p.id
                       WHERE p.active=1 GROUP BY p.id ORDER BY p.id""")
    rows = db.q("SELECT * FROM templates WHERE COALESCE(status,'ok') NOT IN ('merged','hidden') ORDER BY id")

    # состав продуктов — одним запросом (раньше был N+1 запрос на каждый шаблон)
    pd_rows = db.q("""SELECT pd.product_id, pd.template_id, pd.sort_order,
                             t.title, t.code, t.pages, t.status, t.reviewed, t.doc_index
                      FROM product_documents pd JOIN templates t ON t.id=pd.template_id
                      ORDER BY COALESCE(t.doc_index, 999), pd.sort_order, t.title""")
    by_prod, attached = {}, set()
    for r in pd_rows:
        by_prod.setdefault(r["product_id"], []).append(r)
        attached.add(r["template_id"])

    def _prod_fold(p) -> str:
        """Сворачиваемая карточка продукта: название — кнопка, внутри — документы с кнопкой удаления."""
        empty_html = '<div class="muted" style="padding:4px 2px">В продукте нет документов</div>'
        docs = by_prod.get(p["id"], [])
        have = {d["template_id"] for d in docs}
        rows_html = ""
        for d in docs:
            ok = bool(d.get("reviewed"))
            no = d.get("doc_index") or d["template_id"]
            rows_html += item(
                "📄",
                f'{d["title"]}',
                sub=f'{d["pages"] or 0} стр. · {d["code"]}',
                tone="green" if ok else "violet", go=False,
                href=f'/templates/product/{p["id"]}/constructor?tpl={d["template_id"]}',
                extra=f'<span class="badge doc-no">№{no}</span> '
                      f'<button type="button" class="prod-doc-del" data-remove-doc="{d["template_id"]}" '
                      f'data-product="{p["id"]}" title="Убрать документ из этого продукта">✕ Убрать</button>')
        free = [t for t in rows if t["id"] not in have]
        add_html = ""
        if free:
            opts = "".join(f'<option value="{t["id"]}">{t["title"]}</option>' for t in free)
            add_html = (
                f'<form class="prod-add" method="post" action="/templates/product/{p["id"]}/add-doc">'
                f'<select name="template_id" aria-label="Выбрать документ">{opts}</select>'
                f'<button class="btn sm" type="submit">+ Добавить документ</button></form>')
        info_btn = (f'<button type="button" class="prod-info-btn" data-modal="m_prod_{p["id"]}" '
                    f'title="Что это за виза, кому подходит, срок, документы">'
                    f'<span class="pi-full">ℹ️ О продукте</span><span class="pi-mini">ℹ️</span></button>'
                    f'<a class="prod-info-btn prod-ctor-btn" '
                    f'href="/templates/product/{p["id"]}/constructor" '
                    f'title="Конструктор группы: все документы этого продукта вместе, '
                    f'общие переменные — одни на всю группу">'
                    f'<span class="pi-full">🛠 Конструктор продукта</span>'
                    f'<span class="pi-mini">🛠</span></a>')
        return ui_card(_short(p), (rows_html or empty_html) + add_html + _client_docs_short(p),
                       emoji=PRODUCT_EMOJI.get(p["code"], "📦"), tone="blue",
                       note=f'{len(docs)} док.', head_extra=info_btn)

    def _prod_modal(p) -> str:
        """Всплывающее описание продукта: аккуратная шапка + разделы «метка — текст»."""
        info = PRODUCT_INFO.get(p["code"], {})
        docs_n = len(by_prod.get(p["id"], []))
        desc = (p.get("description") or "")
        price = re.search(r"price_idr=([0-9]+)", desc)
        stat = re.search(r"status=([a-z_]+)", desc)
        smap = {"ready": "готов", "implemented": "внедрён", "researched": "изучен", "draft": "черновик"}
        badges = f'<span class="pi-badge">📄 документов в комплекте: {docs_n}</span>'
        if price:
            badges += ('<span class="pi-badge">💰 цена: '
                       + f'{int(price.group(1)):,}'.replace(",", " ") + ' IDR</span>')
        if stat:
            badges += (f'<span class="pi-badge">⚙️ статус: '
                       f'{smap.get(stat.group(1), stat.group(1))}</span>')
        sections = "".join(
            f'<div class="pi-section"><div class="pi-label">{lbl}</div>'
            f'<div class="pi-text">{info.get(key) or "—"}</div></div>'
            for key, lbl in (("what", "Что это за виза"), ("who", "Кому подходит"),
                             ("term", "Срок"), ("docs", "Документы комплекта"),
                             ("flow", "Как проходит оформление")))
        hero = (f'<div class="pi-hero">'
                f'<div class="pi-title">{PRODUCT_EMOJI.get(p["code"], "📦")} {_short(p)}</div>'
                f'<div class="pi-sub">{p.get("name") or ""}</div>'
                f'<div class="pi-badges">{badges}</div></div>')
        return modal(f"m_prod_{p['id']}", "Описание продукта", hero + sections)

    product_blocks = "".join(_prod_fold(p) for p in products)
    product_modals = "".join(_prod_modal(p) for p in products)
    if not products:
        product_blocks = '<div class="muted" style="padding:6px 2px">Продуктов пока нет.</div>'

    orphan_rows = [t for t in rows if t["id"] not in attached]
    if orphan_rows:
        body_orphan = "".join(
            item("📄", t["title"],
                 sub=f'{t["pages"] or 0} стр. · {"✅ проверен" if t.get("reviewed") else "⚠️ требует проверки"}',
                 tone="amber", href=f'/templates/{t["id"]}',
                 extra=f'<span class="badge {STATUS_LABEL.get(t["status"], ("", ""))[1]}>'
                       f'{STATUS_LABEL.get(t["status"], ("черновик", ""))[0]}</span>'
                       f' <a class="badge bad" style="cursor:pointer;text-decoration:none" '
                       f'data-toggle-reviewed="{t["id"]}">⚠️ требует проверки</a>')
            for t in orphan_rows)
        product_blocks += ui_card("Без привязки к продукту", body_orphan,
                                   emoji="🧩", tone="amber", note=str(len(orphan_rows)))

    # «Готова» = у каждой переменной документа есть значение или пример (подтянуто из данных
    # клиента / Drive / генерации). Зелёные галочки для этого не нужны — они только для разработки.
    _ready_map = {}
    for _r in db.q("""SELECT template_id,
                            COUNT(*) AS total,
                            SUM(CASE WHEN TRIM(COALESCE(default_value,'')) <> ''
                                       OR (COALESCE(examples_json,'') NOT IN ('', '[]'))
                                     THEN 1 ELSE 0 END) AS ok
                     FROM template_variables
                     WHERE name NOT IN ('period_from','period_to','balance_words','balance_cents',
                                        'doc_no','ref_no','card_mask','doc_date','balance_rub','balance_value')
                     GROUP BY template_id"""):
        _ready_map[_r["template_id"]] = (int(_r["total"] or 0), int(_r["ok"] or 0))
    grouped = _group_by_type(rows)
    type_blocks = ""
    group_modals = ""
    for title, items in grouped:
        body = ""
        for t in items:
            emoji, mark = _icon_for(t["code"], t.get("reviewed"))
            sub = f'{t["pages"] or 0} стр. · {t["code"]}'
            _tot, _ok = _ready_map.get(t["id"], (0, 0))
            _ready = _tot > 0 and _ok == _tot
            ready_badge = ('<span class="badge ok">Готова</span>' if _ready
                           else '<span class="badge bad">Не готова</span>')
            body += item(emoji, t["title"], sub=sub, href=f'/templates/{t["id"]}',
                         tone="green" if _ready else "violet",
                         extra=f'<span class="badge doc-no">№{t.get("doc_index") or t["id"]}</span> '
                               f'{ready_badge}')
        all_ok = all(_ready_map.get(t["id"], (0, 0))[0] > 0
                     and _ready_map.get(t["id"], (0, 0))[0] == _ready_map.get(t["id"], (0, 0))[1]
                     for t in items)
        _gi = _group_info(title)
        _extra = ""
        if _gi:  # кнопка «ℹ️» — в одном стиле с кнопкой «О продукте»
            _slug = _group_slug(title)
            _extra = (f'<button type="button" class="prod-info-btn" data-modal="m_grp_{_slug}" '
                      f'title="Что это за документы, кому нужны, как делаются">'
                      f'<span class="pi-full">ℹ️ О документах</span>'
                      f'<span class="pi-mini">ℹ️</span></button>')
            group_modals += _group_modal(_slug, title, [x["title"] for x in items], _gi)
        type_blocks += ui_card(title, body,
                               emoji="✅" if all_ok else "📚",
                               tone="green" if all_ok else "amber",
                               note=f'{len(items)} шт.', head_extra=_extra)

    products_for_select = db.q("SELECT id, code, name FROM products WHERE active=1 ORDER BY id")
    product_options = "".join(
        f'<option value="{p["id"]}">{_short(p)}</option>' for p in products_for_select)

    upload_form = f"""
<form method="post" action="/templates/upload" enctype="multipart/form-data">
  <label for="t_title">Название документа</label>
  <input id="t_title" type="text" name="title" placeholder="например: Справка о зарплате" required>
  <label for="t_product">Продукт</label>
  <select id="t_product" name="product_id" required>{product_options}</select>
  <label for="t_file">PDF-эталон (до {MAX_UPLOAD_MB} МБ)</label>
  <input id="t_file" type="file" name="file" accept="application/pdf" required>
  <button class="btn block" type="submit" style="margin-top:14px">Загрузить</button>
</form>"""

    add_product_form = """
<form method="post" action="/templates/add_product">
  <label for="ap_code">Код (латиницей)</label>
  <input id="ap_code" name="code" placeholder="KITAS" required>
  <label for="ap_name">Полное название</label>
  <input id="ap_name" name="name" placeholder="Виза KITAS" required>
  <label for="ap_desc">Описание</label>
  <textarea id="ap_desc" name="description" rows="2"></textarea>
  <button class="btn block" type="submit" style="margin-top:14px">Создать продукт</button>
</form>"""

    divider = '<hr style="border:none;border-top:2px solid #22c55e;margin:18px 0 12px">'
    type_header = ('<h2 class="sect-h">📚 Все документы по типу '
                   '<span style="font-weight:600;font-size:14px;color:#4B6B58">'
                   '(редактирование шаблона документа)</span></h2>')
    type_sub = '<div class="page-sub">Группировка для ручной проверки. Кликни ⚠️ — отметит как «проверен».</div>'

    body = f"""
<h1>Конструктор PDF</h1>
<div class="page-sub">{len(rows)} шаблонов в {len(products)} продуктах. Нажмите продукт, чтобы увидеть его документы.</div>
<div class="row tight">
  {modal_button("+ Загрузить PDF-шаблон", "m_upload", cls="btn")}
  {modal_button("+ Добавить продукт", "m_add_product", cls="btn ghost")}
</div>
<h2 class="sect-h" style="display:none">📦 Продукты</h2>
<details class="fold-all" id="fold-products">
  <summary class="fa-head">
    <span class="fa-title">📦 Продукты</span>
    <span class="fa-note">Здесь только состав продукта: какой документ в него входит — добавить или убрать. Сам документ здесь не редактируется: редактор (переменные, оригинал, разметка) — в разделе «Все документы по типу» ниже.</span>
    <span class="fa-count">{len(products)} шт.</span>
    <span class="chev">›</span>
  </summary>
  <div class="fa-body">
{product_blocks}
  </div>
</details>
{product_modals}
{group_modals}
<style>
/* Оформление плашек продуктов — в одном стиле с разделом «Все документы по типу» */
.prod-info-btn {{ flex:0 0 auto; border:1px solid #93C5FD; background:#EFF6FF; color:#1D4ED8;
                  border-radius:8px; padding:4px 11px; font-size:12px; font-weight:700;
                  cursor:pointer; white-space:nowrap; font-family:inherit;
                  display:inline-flex; align-items:center; justify-content:center;
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
.card summary .prod-info-btn {{ margin-left:12px; margin-right:8px; flex:0 0 auto; }}
/* Выравнивание: колонка названия продукта фиксированной ширины —
   кнопка «О продукте» встаёт на одну вертикаль у всех продуктов */
.card summary:has(.prod-info-btn) {{ display:flex; align-items:center; gap:8px; }}
/* Название — полностью, без обрезки; счётчик «N шт.» — в одну вертикаль правее, к кнопке */
.fa-body .card summary > span:first-of-type,
.card summary:has(.prod-info-btn) > span:first-of-type {{
  flex:0 1 auto; white-space:nowrap; overflow:visible; text-overflow:clip; }}
.fa-body .card summary .muted,
.card summary:has(.prod-info-btn) .muted {{
  flex:1 1 auto; text-align:right; padding-right:2px; margin-left:0; }}
.pi-mini {{ display:none; }}
/* у карточки без кнопки «ℹ️» счётчик сдвигаем на её ширину — вертикаль счётчиков одинаковая */
.fa-body .card summary:not(:has(.prod-info-btn)) .muted {{ margin-right:155px; }}

/* === Мобильная версия: компактно, без «расплывания» === */
@media (max-width: 720px) {{
  .topbar {{ background:#fff; }}
  .sect-h {{ margin-top:22px; font-size:17px; }}
  .sect-sub {{ font-size:12px; margin-bottom:9px; }}
  /* плашка продукта: [иконка] название [N док.] [ℹ️] — одна строка, без обрезки */
  .card summary:has(.prod-info-btn) {{ flex-wrap:nowrap; gap:6px; padding:12px 12px; }}
  .card summary:has(.prod-info-btn) > span:first-of-type {{
    flex:1 1 auto; min-width:0; white-space:normal; font-size:14.5px; line-height:1.25; }}
  .card summary:has(.prod-info-btn) .muted {{ flex:0 0 auto; font-size:12px; }}
  .prod-info-btn {{ margin:0; padding:5px 9px; min-width:0; }}
  .pi-full {{ display:none; }}
  .pi-mini {{ display:inline; font-size:14px; }}
  .card .body {{ padding:8px 10px 12px; }}
  /* документы внутри: название в 1–2 строки, значки — на второй строке */
  .item {{ flex-wrap:wrap; align-items:flex-start; gap:8px; padding:10px 2px; }}
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
.pi-title {{ font-size:19px; font-weight:800; color:#0F172A; letter-spacing:-0.01em; }}
.pi-sub {{ font-size:12.5px; color:#5B6B60; margin-top:5px; line-height:1.45; }}
.pi-badges {{ margin-top:9px; display:flex; flex-wrap:wrap; gap:6px; }}
.pi-badge {{ display:inline-block; background:#E7F6EC; color:#15803D; border:1px solid #BFE0CB;
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
.fold-all > summary.fa-head {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap;
             cursor:pointer; padding:14px 16px; background:#F6FAF8; border-bottom:1px solid #EDF3EF;
             list-style:none; }}
.fold-all > summary.fa-head::-webkit-details-marker {{ display:none; }}
.fold-all > summary.fa-head::marker {{ content:""; }}
.fold-all:not([open]) > summary.fa-head {{ border-bottom:none; }}
.fa-title {{ font-size:17.5px; font-weight:900; color:#111827; letter-spacing:-0.01em; }}
.fa-note {{ flex:1 1 260px; font-size:12.5px; color:#6B7C70; line-height:1.4; }}
.fa-count {{ flex:0 0 auto; font-size:12px; font-weight:800; color:#15803D; background:#E7F6EC;
             border:1px solid #BFE0CB; border-radius:10px; padding:2px 9px; }}
.fold-all > summary.fa-head .chev {{ flex:0 0 auto; color:#9AA3B2; font-size:20px;
             transition:transform .18s; }}
@media (max-width:720px) {{
  /* Телефон: стрелка раскрытия закреплена в углу и не уезжает за блок */
  .fold-all > summary.fa-head {{ position:relative; padding:13px 40px 13px 14px; }}
  .fold-all > summary.fa-head .chev {{ position:absolute; right:13px; top:13px; }}
  .fa-note {{ flex:1 1 100%; }}
  .fa-head {{ gap:8px; }}
  /* Любой раскрывающийся блок на телефоне: стрелка в правом углу, без вылезания */
  details > summary {{ position:relative; padding-right:36px; }}
  details > summary .chev, details > summary .prod-chev {{
    position:absolute; right:12px; top:50%; transform:translateY(-50%); flex:0 0 auto; }}
  details[open] > summary .chev {{ transform:translateY(-50%) rotate(90deg); }}
  details[open] > summary .prod-chev {{ transform:translateY(-50%) rotate(180deg); }}
}}
.fold-all[open] > summary.fa-head .chev {{ transform:rotate(90deg); }}
.fa-body {{ padding:12px 12px 4px; display:flex; flex-direction:column; gap:10px; }}
/* Компактнее: карточки продуктов и строки документов внутри блоков стоят ближе */
.fa-body {{ gap:4px; padding:7px 8px 1px; }}
.fa-body .card, .fa-body > .card {{ margin:0 !important; }}
.fa-body .card > summary, .fa-body .card summary {{ padding:10px 12px; gap:9px; }}
.fa-body .card .body {{ padding:4px 10px 8px; }}
.fa-body .item {{ padding:7px 2px; gap:9px; }}
.fa-body .item .ico {{ width:36px; height:36px; border-radius:10px; font-size:16px; }}
.fa-body .item .t {{ font-size:14.5px; line-height:1.3; }}
.fa-body .item .s {{ font-size:11.5px; margin-top:0; }}
.fa-body .item:first-child {{ border-top:none; }}
.fa-body .prod-add {{ margin-top:6px; padding-top:7px; gap:6px; }}
/* крошки в шапке сайта */
.crumb-bar .tpl-crumbs {{ margin:0; }}
</style>
{divider}
<details class="fold-all" id="fold-types" open>
  <summary class="fa-head">
    <span class="fa-title">📚 Все документы по типу <span style="font-weight:600;font-size:13px;color:#4B6B58">(редактирование шаблона документа)</span></span>
    <span class="fa-note">Отсюда открывается сам документ: поля переменных, HTML-шаблон, оригинальный пример с разметкой и перевод. Надпись «Готова» появляется сама, когда у каждой переменной документа есть значение или пример — зелёные галочки для этого не требуются.</span>
    <span class="fa-count">{len(rows)} шт.</span>
    <span class="chev">›</span>
  </summary>
  <div class="fa-body">
{type_blocks}
  </div>
</details>
{modal("m_upload", "Загрузить PDF-шаблон", upload_form)}
{modal("m_add_product", "Новый продукт", add_product_form)}
<script>
document.addEventListener("click", async (e)=>{{
  const b = e.target.closest("[data-toggle-reviewed]");
  if (!b) return;
  e.preventDefault();
  const id = b.dataset.toggleReviewed;
  const r = await fetch(`/templates/${{id}}/toggle-reviewed`, {{method:"POST"}});
  const d = await r.json();
  if (d.ok) location.reload();
  else alert(d.error || "ошибка");
}});

// Убрать документ из продукта (без перезагрузки страницы не выйдет — список пересобирается)
document.addEventListener("click", async (e)=>{{
  const b = e.target.closest("[data-remove-doc]");
  if (!b) return;
  e.preventDefault();
  const tpl = b.dataset.removeDoc, prod = b.dataset.product;
  const rowTitle = (b.closest(".item")?.querySelector(".t")?.textContent || "").trim();
  if (!confirm("Убрать документ «" + rowTitle + "» из этого продукта? Сам шаблон останется в системе.")) return;
  b.disabled = true; b.textContent = "…";
  const fd = new FormData(); fd.append("template_id", tpl);
  const r = await fetch(`/templates/product/${{prod}}/remove-doc`, {{method:"POST", body:fd}});
  const d = await r.json();
  if (d.ok) location.reload(); else {{ b.disabled = false; b.textContent = "✕ Убрать"; alert(d.error || "ошибка"); }}
}});
</script>
"""
    return render("Конструктор PDF", "templates", body)

@bp.route("/templates/add_product", methods=["POST"])
@login_required
def add_product():
    code = (request.form.get("code") or "").strip()
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    if not code or not name:
        flash("Укажите код и название", "error")
        return redirect(url_for("templates.page"))
    code = _safe_name(code).upper()
    if db.q1("SELECT id FROM products WHERE code=?", (code,)):
        flash(f"Продукт с кодом {code} уже есть", "error")
        return redirect(url_for("templates.page"))
    db.exec_sql("INSERT INTO products (code, name, description, active) VALUES (?,?,?,1)",
                (code, name, description))
    db.log_event("product", 0, "created", payload=f"{code} {name}")
    flash(f"Продукт «{name}» создан")
    return redirect(url_for("templates.page"))


@bp.route("/templates/product/<int:product_id>/add-doc", methods=["POST"])
@login_required
def add_product_doc(product_id: int):
    """Добавить существующий документ (шаблон) в продукт."""
    tpl_id = int(request.form.get("template_id") or 0)
    t = db.q1("SELECT id, code, title FROM templates WHERE id=?", (tpl_id,))
    p = db.q1("SELECT id, code FROM products WHERE id=?", (product_id,))
    if not t or not p:
        flash("Документ или продукт не найден", "error")
        return redirect(url_for("templates.page"))
    if db.q1("SELECT 1 FROM product_documents WHERE product_id=? AND template_id=?",
             (product_id, tpl_id)):
        flash("Этот документ уже есть в продукте", "error")
        return redirect(url_for("templates.page"))
    # слот = префикс кода до «__» (варианты одного документа попадают в один слот)
    slot = t["code"].split("__")[0] or t["code"]
    so = (db.q1("SELECT COALESCE(MAX(sort_order),0)+10 AS so FROM product_documents WHERE product_id=?",
                (product_id,)) or {}).get("so", 10)
    same_slot = db.q1("""SELECT COUNT(*) AS n FROM product_documents pd JOIN templates x ON x.id=pd.template_id
                         WHERE pd.product_id=? AND pd.slot_code=?""", (product_id, slot)) or {}
    db.exec_sql("""INSERT INTO product_documents
                   (product_id, template_id, required, sort_order, slot_code, is_default, slot_part)
                   VALUES (?,?,1,?,?,?,1)""",
                (product_id, tpl_id, so, slot, 0 if (same_slot.get("n") or 0) else 1))
    try:
        db.log_event("product", product_id, "doc_added", payload=f'{p["code"]} + {t["code"]}')
    except Exception:
        pass
    flash(f'Документ «{t["title"]}» добавлен в продукт «{p["code"]}»')
    return redirect(url_for("templates.page"))


@bp.route("/templates/product/<int:product_id>/remove-doc", methods=["POST"])
@login_required
def remove_product_doc(product_id: int):
    """Убрать документ из продукта (сам шаблон не удаляется)."""
    tpl_id = int(request.form.get("template_id") or 0)
    row = db.q1("""SELECT pd.id, t.title, t.code FROM product_documents pd
                   JOIN templates t ON t.id=pd.template_id
                   WHERE pd.product_id=? AND pd.template_id=?""", (product_id, tpl_id))
    if not row:
        return jsonify({"ok": False, "error": "документа нет в продукте"}), 404
    db.exec_sql("DELETE FROM product_documents WHERE id=?", (row["id"],))
    # если в слоте не осталось «основного» варианта — назначим первый оставшийся
    db.exec_sql("""UPDATE product_documents SET is_default=1 WHERE product_id=? AND slot_code=?
                   AND id=(SELECT MIN(id) FROM product_documents WHERE product_id=? AND slot_code=?)""",
                (product_id, row["code"].split("__")[0], product_id, row["code"].split("__")[0]))
    try:
        db.log_event("product", product_id, "doc_removed", payload=row["code"])
    except Exception:
        pass
    return jsonify({"ok": True, "removed": row["title"]})


def _group_by_type(rows):
    """Группируем шаблоны по логическим группам: банковские справки, CV, контракты,
    письма и т.д. — на основе префикса кода (bank_statement_*, cv_*, bridging_*, ...)."""
    groups = {}
    order = []
    def key(code):
        if code.startswith("bank_statement"): return "Банковские справки"
        if code.startswith("cv"): return "Резюме (CV)"
        if code.startswith("remote_work_agreement"): return "Remote Work Agreement"
        if code.startswith("d12"): return "D12 (ходатайства)"
        if code.startswith("statement_letter_e02"): return "Statement Letter (E-02)"
        if code.startswith("bridging_") or code.startswith("conversion_"):
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
    if code.startswith("bank_statement"): emoji = "🏦"
    elif code.startswith("cv"): emoji = "👤"
    elif code.startswith("remote_work_agreement"): emoji = "📝"
    elif code.startswith("d12"): emoji = "📄"
    elif code.startswith("statement_letter_e02"): emoji = "✉️"
    elif code.startswith("bridging_") or code.startswith("conversion_"): emoji = "✉️"
    mark = "✅" if reviewed else "⚠️"
    return emoji, mark


def _group_vars_panel(product_id: int, template_id: int) -> str:
    """Общие переменные продукта: одна правка — во все документы группы.

    Заказчик работает в конструкторе не с отдельным документом, а с продуктом целиком:
    ФИО, дата рождения, паспорт — одна переменная на всю группу (мостовая виза → везде одна
    и та же), поэтому значения задаются здесь один раз и раскладываются по всем документам.
    """
    import html as _html
    if not product_id:
        return ''
    prod = db.q1("SELECT id, code, name FROM products WHERE id=?", (product_id,)) or {}
    docs = db.q("SELECT t.id, t.title, t.code, t.doc_index FROM templates t "
                "JOIN product_documents pd ON pd.template_id=t.id "
                "WHERE pd.product_id=? AND COALESCE(t.status,'ok') NOT IN ('merged','hidden') "
                "ORDER BY pd.sort_order, COALESCE(t.doc_index, 999), t.title", (product_id,)) or []
    if len(docs) < 2:
        return ''
    vars_by_name: dict[str, dict] = {}
    for d in docs:
        for v in db.q("SELECT name, label, default_value FROM template_variables "
                      "WHERE template_id=?", (d["id"],)) or []:
            nm = v["name"]
            rec = vars_by_name.setdefault(nm, {"docs": [], "value": "", "label": v["label"] or ""})
            rec["docs"].append(d["title"] or d["code"])
            if not rec["value"] and (v["default_value"] or "").strip():
                rec["value"] = (v["default_value"] or "").strip()
            if not rec["label"] and v["label"]:
                rec["label"] = v["label"]
    shared = [(nm, r) for nm, r in vars_by_name.items() if len(r["docs"]) >= 2]
    shared.sort(key=lambda x: (-len(x[1]["docs"]), x[0]))
    if not shared:
        return ''
    rows = []
    for nm, r in shared:
        label = r["label"] or nm
        rows.append(
            '<div class="gv-row">'
            f'<label class="gv-name" for="gv_{nm}">{_html.escape(label)}'
            f'<span class="gv-nm mono"> · {nm}</span>'
            f'<span class="gv-docs">{len(r["docs"])} док.: '
            f'{_html.escape(", ".join(r["docs"][:3]))}'
            f'{"…" if len(r["docs"]) > 3 else ""}</span></label>'
            f'<input id="gv_{nm}" type="text" name="{nm}" '
            f'value="{_html.escape(r["value"])}" placeholder="значение для всех документов">'
            '</div>')
    inner = ''.join(rows)
    head = (f'🧩 Общие переменные продукта · {_html.escape(SHORT_NAME.get(prod.get("code"), prod.get("name") or ""))}')
    hint = (f'Документов в группе: {len(docs)} · общих переменных: {len(shared)}. '
            'Значение, заданное здесь, подставляется во все документы группы.')
    return (f'<div class="grp-vars" id="grp-vars">'
            f'<div class="gv-head">{head}</div>'
            f'<div class="gv-hint">{_html.escape(hint)}</div>'
            f'<form method="post" action="/templates/product/{product_id}/save-shared">'
            f'<div class="gv-rows">{inner}</div>'
            f'<div class="gv-actions"><button class="btn sm" type="submit">'
            f'💾 Сохранить во все документы группы</button>'
            f'<span class="muted">действует на {len(docs)} документ(ов) этого продукта</span>'
            f'</div></form></div>')


def _client_docs_short(product) -> str:
    """Строки «дополнительно от клиента» под чертой в карточке продукта.

    Заказчик хочет видеть это как обычный список строк (в том же стиле, что и документы
    продукта): «Дополнительные документы от клиента», ниже — по строке на документ, справа
    у каждой строки пометка «обязательно» / «необязательно». Без кружков, бейджей и пояснений.
    """
    import html as _html
    try:
        import json as _json
        from pathlib import Path as _Path
        m = _json.loads((_Path('/opt/wolf_v2/data/guide/client_docs_matrix.json'))
                        .read_text(encoding='utf-8'))
    except Exception:  # noqa: BLE001
        return ''
    code = (product or {}).get('code') if isinstance(product, dict) else None
    pdata = (m.get('products') or {}).get(code or '', {})
    minimum = [str(x) for x in (m.get('minimum') or [])]
    docs = pdata.get('documents') or {}

    def need_label(raw: str) -> tuple[str, str]:
        low = (raw or '').strip().lower()
        if low.startswith('обяз'):
            return 'обязательно', 'req'
        if low.startswith('необяз'):
            return 'необязательно', 'opt'
        if low in ('по ситуации', 'опционально', 'по запросу', ''):
            return 'необязательно', 'opt'
        return _html.escape(raw.strip()), 'opt'

    lines = []
    seen = set()
    for name in minimum:
        key = re.sub(r'[^а-яa-z0-9]+', '', name.lower())
        seen.add(key)
        lines.append('<div class="pc-line"><span class="pc-name">%s</span>'
                     '<span class="pc-need req">обязательно</span></div>' % _html.escape(name))
    for label, d in docs.items():
        key = re.sub(r'[^а-яa-z0-9]+', '', label.lower())
        if key in seen:          # уже есть строкой выше (в минимуме) — не повторяем
            continue
        seen.add(key)
        lbl, tone = need_label(d.get('need') or '')
        lines.append('<div class="pc-line"><span class="pc-name">%s</span>'
                     '<span class="pc-need %s">%s</span></div>'
                     % (_html.escape(label), tone, lbl))
    if not lines:
        return ''
    return ('<hr class="prod-sep">'
            '<div class="prod-client">'
            '<div class="pc-head">Дополнительные документы от клиента</div>'
            + ''.join(lines) + '</div>')


def _client_docs_block(product=None) -> str:
    """Что клиент даёт по этому продукту: минимум, документы и переменные из них, стоп-условия."""
    import html as _html
    try:
        import json as _json
        from pathlib import Path as _Path
        m = _json.loads((_Path('/opt/wolf_v2/data/guide/client_docs_matrix.json'))
                        .read_text(encoding='utf-8'))
    except Exception:  # noqa: BLE001
        return ''
    code = (product or {}).get('code') if isinstance(product, dict) else None
    pdata = (m.get('products') or {}).get(code or '', {})
    minimum = m.get('minimum') or []
    if not pdata and not minimum:
        return ''
    parts = ['<div class="pk-client">']
    parts.append('<div class="pk-client-ttl">От клиента: что требуется и что система берёт из этих документов</div>')
    parts.append('<div class="pk-cl-row pk-cl-min"><span class="pk-cl-ico">✅</span>'
                 '<span class="pk-cl-name">Минимум для любой заявки</span>'
                 '<span class="pk-cl-det">%s</span><span class="pk-cl-when">обязательно</span></div>'
                 % _html.escape(', '.join(minimum)))
    for label, d in (pdata.get('documents') or {}).items():
        vars_txt = '; '.join('%s → %s' % (v, ', '.join(w[:2]))
                             for v, w in list(d['variables'].items())[:6])
        more = '' if len(d['variables']) <= 6 else ' (и ещё %d)' % (len(d['variables']) - 6)
        parts.append('<div class="pk-cl-row"><span class="pk-cl-ico">🙋</span>'
                     '<span class="pk-cl-name">%s</span>'
                     '<span class="pk-cl-det">%s<br><span class="pk-cl-vars">берём: %s%s</span></span>'
                     '<span class="pk-cl-when">%s</span></div>'
                     % (_html.escape(label), _html.escape(d.get('detail', '')),
                        _html.escape(vars_txt), _html.escape(more), _html.escape(d.get('need', ''))))
    if pdata.get('stop_keys'):
        parts.append('<div class="pk-cl-row pk-cl-stop"><span class="pk-cl-ico">⛔</span>'
                     '<span class="pk-cl-name">Стоп, если нет</span><span class="pk-cl-det">%s</span>'
                     '<span class="pk-cl-when">система не собирает</span></div>'
                     % _html.escape(', '.join(pdata['stop_keys'])))
    parts.append('<div class="pk-cl-row pk-cl-auto"><span class="pk-cl-ico">⚙️</span>'
                 '<span class="pk-cl-name">Сформирует сама</span>'
                 '<span class="pk-cl-det">суммы и суммы прописью, даты и сроки, номера документов, '
                 'формулировки и перечень услуг, справки, письма иммиграции, договоры, резюме, '
                 'организация-работодатель вне Индонезии (из справочника)</span>'
                 '<span class="pk-cl-when">автоматически</span></div>')
    parts.append('<div class="pk-cl-rule">Правило: документ клиента сильнее карточки — при расхождении '
                 'берём значение из документа с Google Диска. Чего нет нигде — оставляем пустым, '
                 'не выдумываем.</div>')
    parts.append('</div>')
    return ''.join(parts)


def _product_documents(product, all_templates) -> str:
    rows = db.q("""SELECT t.* FROM templates t
                   JOIN product_documents pd ON pd.template_id=t.id
                   WHERE pd.product_id=? ORDER BY pd.sort_order, t.title""",
                (product["id"],))
    items = "".join(
        item("📄", t["title"],
             sub=f'{t["pages"] or 0} стр. · {"✅ проверен" if t.get("reviewed") else "⚠️ требует проверки"}',
             href=f'/templates/{t["id"]}', tone="violet",
             extra=f'<span class="badge {STATUS_LABEL.get(t["status"], ("", ""))[1]}">'
                   f'{STATUS_LABEL.get(t["status"], ("черновик", ""))[0]}</span>')
        for t in rows)
    if not items:
        items = '<div class="muted" style="padding:6px 2px">Документов пока нет.</div>'
    return items + _client_docs_block(product)


@bp.route("/templates/upload", methods=["POST"])
@login_required
def upload():
    upload_file = request.files.get("file")
    title = (request.form.get("title") or "").strip()
    product_id = int(request.form.get("product_id") or 0)
    if not upload_file or not upload_file.filename or not title or not product_id:
        flash("Укажите название, продукт и приложите PDF", "error")
        return redirect(url_for("templates.page"))
    if not upload_file.filename.lower().endswith(".pdf"):
        flash("Принимаем только PDF", "error")
        return redirect(url_for("templates.page"))
    data = upload_file.read()
    if data[:5] != b"%PDF-":
        flash("Это не PDF (нет сигнатуры %PDF)", "error")
        return redirect(url_for("templates.page"))

    product = db.q1("SELECT code FROM products WHERE id=?", (product_id,))
    if not product:
        flash("Продукт не найден", "error")
        return redirect(url_for("templates.page"))

    base_code = _safe_name(title).lower()[:30] or f"doc_{datetime.now():%Y%m%d_%H%M%S}"
    code = f"{product['code'].lower()}__{base_code}"
    n = 1
    while db.q1("SELECT id FROM templates WHERE code=?", (code,)):
        n += 1
        code = f"{product['code'].lower()}__{base_code}_{n}"
    path = SOURCES_DIR / f"{code}.pdf"
    path.write_bytes(data)
    template_id = db.exec_sql(
        "INSERT INTO templates (code, title, source_pdf, status) VALUES (?,?,?,'draft')",
        (code, title, path.name))
    db.exec_sql("INSERT INTO product_documents (product_id, template_id, required, sort_order) "
                "VALUES (?,?,?,?)", (product_id, template_id, 1, 0))
    db.log_event("template", template_id, "uploaded", payload=f"{title} ({len(data) // 1024} КБ)")
    flash(f"Шаблон «{title}» загружен — нажмите «Конвертировать PDF → HTML»")
    return redirect(url_for("templates.card", template_id=template_id))


@bp.route("/templates/<int:template_id>")
@login_required
def card(template_id: int, _app_id: int | None = None, _embed: bool = False,
         _product_id: int | None = None):
    """Конструктор документа. _app_id/_embed — служебные: страница заявки встраивает
    ту же рабочую область (миниатюры + визор + переменные) с данными заявки.
    _product_id — конструктор продукта: работаем группой документов этого продукта,
    в колонке миниатюр только они, а общие переменные задаются один раз на всю группу."""
    t = _template(template_id)
    _prod = (db.q1("SELECT id, code, name FROM products WHERE id=?", (_product_id,))
             if _product_id else None)
    # Контекст для окна сравнения: продукт · заявка · документ (требование Андрея, 06.10.2026).
    # Считаем сразу: он нужен в шапке и в подписи кнопки «Сравнение».
    _cmp_parts = []
    if _prod:
        _cmp_parts.append('Конструктор продукта «%s»'
                          % (SHORT_NAME.get(_prod.get("code"), _prod.get("name") or _prod.get("code") or "")))
    if _app_id:
        _cmp_parts.append('Заявка №%s' % _app_id)
    if _prod and _app_id:
        _ids_seq = [r["id"] for r in db.q(
            """SELECT t.id FROM product_documents pd JOIN templates t ON t.id=pd.template_id
               WHERE pd.product_id=? AND COALESCE(t.status,'ok') NOT IN ('merged','hidden')
               ORDER BY pd.sort_order, COALESCE(t.doc_index,999), t.title""", (_prod["id"],)) or []]
        _ttl = db.q1("SELECT title FROM templates WHERE id=?", (template_id,)) or {}
        if template_id in _ids_seq:
            _cmp_parts.append('Документ №%s — %s'
                              % (_ids_seq.index(template_id) + 1, _ttl.get("title") or ""))
        elif _ttl.get("title"):
            _cmp_parts.append('Документ — %s' % _ttl["title"])
    _cmp_context = " · ".join(_cmp_parts)
    _cmp_ctx_esc = _cmp_context.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    # ?app=<id> — режим заявки: редактируем документ конкретной заявки её данными
    app_id = request.args.get("app", type=int) if _app_id is None else _app_id
    app_row = db.application_get(app_id) if app_id else None
    if app_id and not app_row:
        app_id = None
    client = (db.client_get(app_row["client_id"]) if app_row else {}) or {}
    variables = db.q("SELECT * FROM template_variables WHERE template_id=? ORDER BY sort_order, name",
                     (template_id,))
    qa = json.loads(t["qa_json"]) if t["qa_json"] else {}

    products_for_template = db.q("""SELECT p.id, p.code, p.name FROM products p
                                    JOIN product_documents pd ON pd.product_id=p.id
                                    WHERE pd.template_id=? ORDER BY p.name""",
                                 (template_id,))
    products_html = "".join(
        f'<span class="badge ok">{PRODUCT_EMOJI.get(p["code"], "📦")} {SHORT_NAME.get(p["code"], p["name"])}</span>'
        for p in products_for_template) or '<span class="muted">не привязан</span>'

    qa_html = ""
    if qa:
        def mark(ok: bool, text: str) -> str:
            return f'<span class="badge {"ok" if ok else "bad"}">{text}</span>'
        qa_html = (
            '<div class="row">'
            + mark(qa.get("ok"), "сверка: " + ("совпадает" if qa.get("ok") else "есть расхождения"))
            + mark(not qa.get("missing_words"), f'потерянных слов: {len(qa.get("missing_words") or [])}')
            + mark(not qa.get("extra_ink"), f'лишней заливки: {len(qa.get("extra_ink") or [])}')
            + mark(not qa.get("leftover_vars"), f'незаполненных: {len(qa.get("leftover_vars") or [])}')
            + f'<span class="badge">стр. {qa.get("pages_out")}/{qa.get("pages_src")}</span></div>')

    def _cv_group(name: str):
        """Рамка для группы переменных — по логике самого документа резюме."""
        if name in ('cv_name', 'cv_profession', 'cv_position_ru'):
            return ('head', '🧾 Шапка документа', 'Имя и должность — как в шапке резюме')
        if name in ('cv_summary', 'cv_skills_hard', 'cv_skills_soft', 'cv_skills_tools',
                    'cv_languages'):
            return ('about', '📝 Описательные данные', 'Профиль, навыки, языки')
        if re.match(r'cv_job1_', name):
            return ('job1', '🏢 Текущее место работы',
                    'Должность, период, организация, обязанности')
        if re.match(r'cv_job\d+_\d+_', name) or re.match(r'cv_job\d+_', name):
            return ('jobN', '🏢 Предыдущее место работы',
                    'Прошлые места: должность, период, организация, обязанности')
        if name in ('cv_education_degree', 'cv_education_school'):
            return ('edu', '🎓 Образование',
                    'Степень и учебное заведение — список зависит от города рождения')
        if name in ('cv_date_of_birth', 'cv_nationality', 'cv_place_of_birth',
                    'cv_passport_no', 'cv_passport_issue', 'cv_passport_expiry'):
            return ('passport', '🪪 Паспортные данные',
                    'Дата и место рождения, гражданство, паспорт')
        return ('main', '📄 Прочее', '')

    def _field_html(v):
        return (
            f'<div class="var-row" data-var="{v["name"]}">'
            f'<label for="v_{v["name"]}">{v["label"] or v["name"]}'
            f'<span class="muted mono"> · {v["name"]}</span></label>'
            f'<div class="row tight" style="gap:6px;align-items:center">'
            f'<input id="v_{v["name"]}" type="text" name="{v["name"]}" value="{v["default_value"] or ""}" '
            f'class="var-input" style="flex:1;font-size:13px" placeholder="значение по умолчанию">'
            f'</div>'
            f'<details class="rule-note">'
            f'<summary style="cursor:pointer;color:#94a3b8;font-size:12px">📝 правило формирования'
            f'{(v["rule_note"] or "") and " — заполнено" or " — пусто"}</summary>'
            f'<textarea name="rule_{v["name"]}" rows="3" style="width:100%;margin-top:4px;font:12px/1.4 monospace;padding:6px;border:1px solid #334155;border-radius:4px;background:#0f172a;color:#e2e8f0" '
            f'placeholder="Опиши откуда и как формируется значение">{v["rule_note"] or ""}</textarea>'
            f'</details>'
            f'</div>')

    _order, _groups = [], {}
    for v in variables:
        key, title, hint = _cv_group(v["name"])
        if key not in _groups:
            _groups[key] = {"title": title, "hint": hint, "items": []}
            _order.append(key)
        _groups[key]["items"].append(_field_html(v))

    _parts = []
    for key in _order:
        g = _groups[key]
        extra = ''
        if key == 'jobN':
            extra = (f'<button type="button" class="cv-add-job" '
                     f'title="Добавить ещё одно предыдущее место работы">＋ Ещё место работы</button>')
        if len(_order) > 1:
            hint = f'<div class="var-group-hint">{g["hint"]}</div>' if g.get("hint") else ''
            _parts.append(
                f'<div class="var-group var-group-{key}">'
                f'<div class="var-group-h">{g["title"]}'
                f'<span class="tpl-count">{len(g["items"])}</span>{extra}</div>'
                f'{hint}{"".join(g["items"])}</div>')
        else:
            _parts.append("".join(g["items"]))
    fields = "".join(_parts)

    html_exists = (HTML_DIR / t["code"] / "template.html").exists()
    src_url = f"/templates/file/sources/{t['code']}.pdf" if t.get("source_pdf") else ""
    # Вкладка «HTML» в конструкторе показывает СЕРВЕРНЫЙ рендер документа для этой заявки
    # (тот же движок, что печатает PDF). Файл-шаблон с {{переменными}} тут не годится:
    # при подстановке на клиенте длинное значение не сдвигало нижние блоки и давало наложения.
    html_url = (f"/templates/htmlview/{t['id']}?app={request.args.get('app', '')}&fit=1"
                if html_exists else "")

    # Превью PDF: если в URL ?pdf=<filename> — показываем его
    rendered_pdf_name = request.args.get("pdf", "")
    rendered_pdf_url = ""
    if rendered_pdf_name and (RENDER_DIR / rendered_pdf_name).exists():
        rendered_pdf_url = f"/templates/file/renders/{rendered_pdf_name}"

    # Состояние редактирования HTML: переменные из БД + то что в post пришло (если есть)
    html_preview = ""
    if html_exists:
        html_preview = (HTML_DIR / t["code"] / "template.html").read_text(encoding="utf-8")
        # Жёсткое правило вёрстки: любой блок шире печатного поля сужается/переносится,
        # поэтому в визоре конструкции текст не выходит за край листа (см. render.fit_width).
        html_preview = doc_render.fit_width(html_preview)
        # В превью оставим {{ var }} как есть (чтобы было видно что не заполнено)

    # Блок 1 — Оригинал (PDF-эталон) — компактный
    if src_url:
        original_block = (
            f'<div class="row tight" style="gap:6px">'
            f'<a class="btn sm" target="_blank" href="{src_url}">📄 Открыть PDF-эталон</a>'
            f'<span class="muted">исходник для сверки</span>'
            f'</div>'
        )
    else:
        original_block = '<div class="muted">Эталон не загружен</div>'

    # Блок 2 — HTML: основная зона редактирования, большой блок
    if html_exists:
        html_block = (
            f'<div class="zp-preview" data-zoom-pan><div id="html-preview-stage" class="html-stage">{html_preview}</div></div>'
            f'<div class="row tight" style="margin-top:6px">'
            f'<form method="post" action="/templates/{template_id}/save-html" style="flex:1;margin:0">'
            f'<input type="hidden" name="html_content" id="html_content">'
            f'<button class="btn ok block" type="submit" style="font-size:12px;padding:6px" '
            f'onclick="document.getElementById(\'html_content\').value=document.getElementById(\'html-stage\').innerHTML">'
            f'💾 Сохранить HTML и применить переменные</button>'
            f'</form>'
            f'</div>'
        )
    else:
        html_block = (
            f'<div class="muted">HTML не сконвертирован.</div>'
            f'<form method="post" action="/templates/{template_id}/convert">'
            f'<button class="btn block" type="submit">Конвертировать PDF → HTML</button></form>'
        )

    # Блок 3 — переменные (компактные поля + правила формирования)
    pdf_block = (
        f'<div class="tpl-panel-body pl-vars">'
        f'<form method="post" action="/templates/{template_id}/render">'
        f'<div class="kv vars-list" style="max-height:none;overflow:auto;font-size:12.5px">{fields or ""}</div>'
        f'<div class="row tight" style="gap:6px;margin-top:8px">'
        f'<button class="btn ok block" type="submit" style="flex:2;font-size:12.5px;padding:6px">🧪 Сформировать PDF</button>'
        f'<button class="btn block" type="submit" name="action" value="save_rules" style="flex:1;font-size:12.5px;padding:6px">📝 Сохранить только правила</button>'
        f'</div>'
        f'</form>'
        f'</div>'
        if html_exists else
        '<div class="muted">Сначала HTML</div>'
    )

    # Превью сгенерированного PDF
    if rendered_pdf_url:
        preview_block = (
            f'<div class="zp-preview" data-zoom-pan><iframe class="pdf-preview" style="width:794.5px;height:1123px;border:0" src="{rendered_pdf_url}#zoom=100&toolbar=0"></iframe></div>'
            f'<div class="muted" style="font-size:11.5px;text-align:center;margin-top:4px">'
            f'📄 {rendered_pdf_name}</div>'
        )
    else:
        preview_block = '<div class="muted" style="padding:24px;text-align:center;font-size:13px">После нажатия «Сформировать PDF» готовый документ появится здесь.</div>'

# === Дефолтные значения для шаблона (для превью) ===
    default_values = json.loads(t.get("default_values_json") or "{}")
    # Список с input-полями (как в карточке заявки) — пользователь может менять значения и видеть подсказки
    RANDOM_VARS = {"doc_no", "ref_no", "card_mask", "balance_rub", "balance_value"}
    # Поля, которые в форме не показываются: считаются автоматически
    # (период справки — от даты формирования назад 3 или 12 месяцев)
    AUTO_HIDDEN = {"period_from", "period_to", "balance_words", "balance_cents"}
    # Поля без выпадающего списка: значение берётся из данных клиента/заявки
    # или генерируется кнопкой — выбирать из истории тут нельзя
    NO_LIST_VARS = RANDOM_VARS | {"doc_date", "client_name", "address_live"}
    # Тесто (образец значения) — короткий пример чтобы админ видел формат
    PLH = {
        'doc_no': 'например BD45789123',
        'ref_no': 'например B19ABCD11EF',
        'card_mask': '220070******6179',
        'inn': '7701234567',
        'phone': '+7 999 123-45-67',
        'email': 'name@example.com',
        'client_name': 'Иванов Иван',
        'name': 'Иванов Иван',
        'full_name': 'Иванов Иван Петрович',
        'full_name_latin': 'IVANOV IVAN',
        'address_live': 'г. Москва, ул. Тверская, 1',
        'address_registration': 'г. Москва, ул. Тверская, 1',
        'date_of_birth': '15.03.1990',
        'birth_date': '15.03.1990',
        'passport_number': '00 00 000000',
        'passport_series': '00 00',
        'money_usd2': '5 000 USD',
        'salary_amount': '545 000',
        'salary_currency': 'RUB',
        'iban': 'BY00 ALFA 3014 0000 4310 1027 0000',
        'agreement_date': '12.05.2024',
        'agreement_start_date': '12.05.2024',
        'agreement_end_date': '11.05.2025',
        'profession': 'Engineer',
        'period_start': '01.06.2026',
        'period_end': '12.09.2026',
        'bank_phone': '+7 800 555-22-22',
        'bank_manager_name': 'E.S. Shadrina',
        'bank_name': 'T-Bank',
    }
    def _tip(txt):
        return (txt or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "&#10;")

    # реально используемые в шаблоне переменные (источник истины — template.html)
    _used = set()
    _pos = {}
    try:
        _h = (HTML_DIR / t["code"] / "template.html").read_text(encoding="utf-8")
        _used = set(re.findall(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", _h))
        _pos = _positional_order(_h)          # порядок как в документе: сверху вниз, слева направо
    except Exception:
        _used = {v["name"] for v in variables}
    _all_vars = list(variables)
    variables = [v for v in _all_vars if v["name"] in _used and v["name"] not in AUTO_HIDDEN]
    variables.sort(key=lambda v: _pos.get(v["name"], (10 ** 9, 10 ** 9, 10 ** 9)))
    _unused = [v for v in _all_vars if v["name"] not in _used]
    # значения из реального примера (первый вариант из базы примеров)
    example_map = {}
    for v in variables:
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
    example_source = {_k: (str(_v).replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\r', '\n')
                           if isinstance(_v, str) else _v)
                      for _k, _v in (example_map or {}).items()}

    # РЕЖИМ ЗАЯВКИ: значения берём из карточки клиента и сохранённых значений заявки,
    # а не из тестового примера. Значения показываем латиницей — как они попадут в документ.
    var_sources = {}
    if app_id and app_row:
        try:
            from blocks.dashboard.page import build_template_values as _btv
            _auto = _btv(client, t["code"]) or {}
            _saved = {}
            _row = db.q1("SELECT values_json FROM application_documents "
                         "WHERE application_id=? AND template_id=?", (app_id, template_id))
            if _row and _row.get("values_json"):
                _saved = json.loads(_row["values_json"]) or {}
            # Значения показываем так, как они уйдут в документ: латиницей.
            # Русский текст в готовых документах недопустим (ФИО, адрес, компания).
            from bot.ai_parser import translit_ru as _tr
            _merged = {**_auto, **_saved}
            _LAT = ("full_name_latin", "client_name_latin", "cv_name", "employee_full_name_latin")
            _fio_lat = next((str(_merged[_k]) for _k in _LAT if _merged.get(_k)), "")
            for _k, _v in _merged.items():
                if _v in (None, ""):
                    continue
                _val = str(_v)
                if _k in ("client_name", "full_name", "employee_name", "employee_full_name",
                          "cv_name", "fio", "director_name", "attorney_name") and _fio_lat:
                    _val = _fio_lat          # ФИО — только латиницей
                else:
                    _val = _tr(_val)         # остальное: кириллица → латиница
                example_map[_k] = _val
            # Происхождение значений (правило для всех документов): зелёный — взято из
            # документов клиента, жёлтый — собрано системой, красный — не разобрались.
            from services.provenance import sources_for as _sources_for
            var_sources.update(_sources_for(_merged, client))
        except Exception as _e:
            log.warning("значения заявки #%s не подставлены: %s", app_id, _e)

    _row_items = []
    _filled_n = 0
    _JOB_FIELD_NUM = {'title': 6, 'period': 7, 'company': 8, 'bullets': 9}

    def _disp_num(name: str, idx: int) -> str:
        """Номер переменной: у дополнительного места — вторым порядком (6.1, 7.1, 8.1, 9.1)."""
        m = re.match(r'cv_job2_(\d+)_(\w+)$', name or '')
        if m:
            base = _JOB_FIELD_NUM.get(m.group(2))
            if base:
                return '%d.%s' % (base, m.group(1))
        return str(idx)
    for i, v in enumerate(variables, 1):
        # №1, №2, №6, №7: кубик — рабочая кнопка, генерирует новое уникальное значение по правилу
        _extra = ""
        if v["name"] == "card_mask":
            try:
                from services.values import bank_bins
                _extra = ' data-bins="' + ",".join(bank_bins((t or {}).get("code") or "")) + '"'
            except Exception:
                _extra = ""
        elif v["name"] in ("balance_rub", "balance_value"):
            try:
                from services.values import balance_bounds
                _lo, _hi = balance_bounds((t or {}).get("code") or "")
                _c = ((t or {}).get("code") or "").lower()
                _fmt = ("dot" if "3m" in _c else "plain") if "sber" in _c else "space"
                _extra = f' data-min="{_lo}" data-max="{_hi}" data-fmt="{_fmt}"'
            except Exception:
                _extra = ""
        if v["name"] == "doc_date":
            # №3: дата формирования документа — календарик возвращает текущую дату
            dice = (f'<button type="button" class="var-today" data-var="{v["name"]}" '
                    f'data-doc="№{t.get("doc_index") or template_id}" '
                    f'title="Подставить текущую дату">📅</button>')
        elif v["name"] in RANDOM_VARS:
            dice = (f'<button type="button" class="var-dice" data-var="{v["name"]}" '
                    f'data-doc="№{t.get("doc_index") or template_id}"{_extra} '
                    f'title="Сгенерировать новое значение по правилу">🎲</button>')
        else:
            dice = ""
        var_name = v["name"]
        cur_val = (example_map.get(var_name) or v.get("default_value") or "").strip()
        if var_name == "doc_date":
            # №3 — дата формирования: на странице всегда стоит текущая дата (не значение из примера)
            from datetime import datetime as _dt_today
            cur_val = _dt_today.now().strftime("%d.%m.%Y")
            example_map[var_name] = cur_val      # значение уходит и в предпросмотр документа
        # Поля с кубиком заполняются сразу при открытии страницы: кубик не создаёт значение
        # впервые, а перегенерирует уже подставленное
        if not cur_val and var_name in RANDOM_VARS:
            try:
                from datetime import datetime as _dtm
                from services.values import gen_doc_no, gen_ref_no, mask_card, gen_balance, number_pattern
                _code = (t or {}).get("code") or ""
                _day = _dtm.now().strftime("%d.%m.%Y")
                if var_name == "doc_no":
                    cur_val = gen_doc_no(_code, _day, _code, pattern=number_pattern(_code, "doc_no"))
                elif var_name == "ref_no":
                    cur_val = gen_ref_no(_code, _day, _code, pattern=number_pattern(_code, "ref_no"))
                elif var_name == "card_mask":
                    cur_val = mask_card("", _code, seed=_code)
                elif var_name in ("balance_rub", "balance_value"):
                    cur_val = gen_balance(_code, seed=_code)
                if cur_val:
                    example_map[var_name] = cur_val      # значение уходит и в предпросмотр HTML
            except Exception:
                cur_val = ""
        # показываем placeholder ИЛИ текущее значение как образец
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
                    safe_ex = ex.replace(chr(34), chr(92)+chr(34)).replace(chr(60), "<").replace(chr(62), ">")
                    opt = '<option value="' + safe_ex + '">'
                    if opt not in parts:
                        parts.append(opt)
            except Exception:
                pass
            for s in sugs:
                val = (s["value"] if isinstance(s, dict) else s[1]) or ""
                safe = val.replace(chr(34), chr(92)+chr(34)).replace(chr(60), "<").replace(chr(62), ">")
                parts.append('<option value="' + safe + '">')
            datalist = '' if var_name in NO_LIST_VARS else '<datalist id="dl_tpl_' + var_name + '">' + "".join(parts) + '</datalist>'
        except Exception:
            pass
        # №1, №2, №6 — не выбор из истории, а генерация по правилу; дата, ФИО и адрес
        # берутся строго из данных клиента и заявки — списки им не нужны
        _list_attr = '' if var_name in NO_LIST_VARS else f' list="dl_tpl_{var_name}"'
        # отображаем значение всегда (если есть), плюс placeholder для тех у кого пусто
        _appr = int(v.get("approved") or 0)
        # Цвет строки = происхождение значения: зелёный/жёлтый/красный (правило заказчика)
        _kind, _note = (var_sources.get(var_name) or ('', ''))[:2]
        if not _kind:
            # Без заявки (пример шаблона) происхождение определяем по самой переменной:
            # сгенерированное кубиком или выбранное из списка — жёлтое, паспортное — зелёное.
            from services.provenance import value_origin as _value_origin
            _kind, _note = _value_origin(var_name, cur_val, None)
        _src_badge = {'real': '🟢', 'synth': '🟡', 'unknown': '🔴'}.get(_kind, '⚪')
        # В инструкции переменной прямо указываем документ и её номер в этом документе:
        # номер берём тот же, что стоит в кружке рядом с полем (единая нумерация в панели).
        _var_no = _disp_num(var_name, i)
        if (cur_val or "").strip():
            _filled_n += 1
        _doc_no = t.get("doc_index") or template_id
        _rule_txt = _tip(v.get("rule_note")) or "Инструкция будет добавлена"
        _tip_full = (
            f'Документ №{_doc_no} — «{_tip(t.get("title") or "")}» · '
            f'переменная №{_var_no} этого документа: {var_name}\n\n{_rule_txt}')
        # У адреса клиента подписываем город обслуживания: от него зависит,
        # какое письмо идёт в комплект — Ngurah Rai (Badung) или Denpasar.
        _city_note = ""
        if var_name in ("address_live", "address_reg", "address") and _app_id:
            try:
                from services import immigration_office as _io
                _oi = _io.resolve_for_app(_app_id)
                if _oi.get("office"):
                    _city_note = (' <span class="var-city" style="color:#15803D;font-weight:600">'
                                  '→ %s</span>' % _tip(_io.office_name(_oi["office"])))
                elif _oi.get("why"):
                    _city_note = (' <span class="var-city" style="color:#8A6100">→ %s</span>'
                                  % _tip(_oi["why"]))
            except Exception:
                _city_note = ""
        # Организация клиента (договор, переменная №1): вместо истории — список
        # организаций из архивных договоров. Один выбор меняет и название в шапке,
        # и реквизиты в подвале: они берутся из одной записи пула.
        _emp_pick = ""
        if var_name == "company_name_in_quotes":
            try:
                from services import employer_pool as _ep
                _eopts = "".join(
                    '<option value="%s"%s>%s</option>' % (
                        _tip(_it["title"]),
                        " selected" if (cur_val or "").strip() == _it["title"].strip() else "",
                        _tip(_it["title"])
                        + ((" · " + _it["city"]) if _it.get("city") else "")
                        + ((" · ИНН " + _it["inn"]) if _it.get("inn") else ""))
                    for _it in _ep.titles())
                if _eopts:
                    # Переменная №1 — организация. Рядом с полем видимый список пула:
                    # выбрал организацию → подтянулись название, адрес, ИНН, КПП, ОГРН;
                    # нужно своё название — выбери «— своё название —» и впиши руками.
                    _emp_pick = ('<select class="emp-pick" data-var="company_name_in_quotes" '
                                 'title="Организация из архива договоров">'
                                 '<option value="">— выберите организацию —</option>'
                                 + _eopts
                                 + '<option value="__own__">— своё название —</option></select>')
                    datalist = '<datalist id="dl_tpl_company_name_in_quotes">%s</datalist>' % _eopts
            except Exception:
                _emp_pick = ""
        _row_items.append((var_name, (
            f'<div class="kv-line var-kind-{_kind}" data-var-row="{var_name}">'
            f'<div class="kv-row">'
            f'<div class="var-line">'
            f'<span class="var-mark var-kind-{_kind}" title="{_src_badge} {_tip(_note)}" aria-hidden="true">●</span>'
            f'<span class="kv-idx">{_disp_num(var_name, i)}</span>'
            f'<input{_list_attr} type="text" name="{var_name}" '
            f'value="{_tip(cur_val)}" '
            f'data-var="{var_name}" '
            f'placeholder="{_tip(sample)}" />'
            f'<span class="var-tools">{dice}</span>'
            f'</div>'
            f'<div class="var-name">'
            f'<span class="var-info" title="{_tip_full}" '
            f'data-var="{var_name}" data-template="{template_id}" '
            f'data-doc="№{_doc_no}" data-num="№{_var_no}" data-docfull="{_tip_full}" '
            f'data-rule="{_tip(v.get("rule_note"))}">i</span>'
            f'<b class="var-ru">{_tip(v.get("label") or var_name)}</b>{_city_note} '
            f'<span class="var-src var-src-{_kind}">{_tip(_note)}</span></div>'
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
        if name in ('cv_education_degree', 'cv_education_school'):
            return ('edu', '🎓 Образование',
                    'Степень и учебное заведение — список зависит от города рождения')
        if name in ('cv_date_of_birth', 'cv_nationality', 'cv_place_of_birth',
                    'cv_passport_no', 'cv_passport_issue', 'cv_passport_expiry'):
            return ('passport', '🪪 Паспортные данные',
                    'Дата и место рождения, гражданство, паспорт')
        if name in ('cv_name', 'cv_profession', 'cv_position_ru'):
            return ('head', '🧾 Шапка документа', '')
        if name in ('cv_summary', 'cv_skills_hard', 'cv_skills_soft', 'cv_skills_tools',
                    'cv_languages'):
            return ('about', '📝 Описательные данные', 'Профиль, навыки, языки')
        return ('', '', '')

    _g_order, _g_items = [], {}
    for _nm, _htm in _row_items:
        _k, _title, _hint = _cv_frame(_nm)
        if _k not in _g_items:
            _g_items[_k] = {"title": _title, "hint": _hint, "html": []}
            _g_order.append(_k)
        _g_items[_k]["html"].append(_htm)

    _g_parts = []
    for _k in _g_order:
        _g = _g_items[_k]
        if not _g["title"]:
            _g_parts.append("".join(_g["html"]))
            continue
        _extra = ''
        if _k == 'jobN':
            _extra = ('<button type="button" class="cv-add-job" '
                      'title="Добавить ещё одно предыдущее место работы">＋ Ещё место работы</button>')
        _hint = f'<div class="var-group-hint">{_g["hint"]}</div>' if _g["hint"] else ''
        _g_parts.append(
            f'<div class="var-group-row"><div class="kv-row">'
            f'<div class="var-group-h">{_g["title"]}'
            f'<span class="tpl-count">{len(_g["html"])}</span>{_extra}</div>'
            f'{_hint}</div></div>' + "".join(_g["html"]))
    var_rows_html = "".join(_g_parts)

    _unused_html = ""
    if _unused:
        _lst = ", ".join(v["name"] for v in _unused[:40])
        _unused_html = (
            '<details class="unused-vars"><summary>Не используются в шаблоне (' + str(len(_unused)) + ')</summary>'
            '<div class="muted" style="font-size:12.5px;line-height:1.6">' + _lst + '</div></details>'
        )

    html_render = ""
    if html_exists:
        _raw = (HTML_DIR / t["code"] / "template.html").read_text(encoding="utf-8")
        _raw = doc_render.fit_width(_raw)      # текст не выходит за печатное поле листа

        def _esc(txt):
            return (str(txt).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

        # авто-значения, которые в форме не показываются (сумма прописью, копейки):
        # считаются из выбранной суммы — в документе они всегда заполнены текстом
        _auto = {}
        try:
            from services.values import build_template_values
            from services.values import fio_full_for_display as _fio_disp
            _ctx = dict(default_values)
            _ctx.update({k: v for k, v in example_map.items() if v})
            for _k in ("client_name", "full_name", "full_name_latin", "cv_name",
                       "employee_name", "employee_full_name", "employee_full_name_latin"):
                if _ctx.get(_k):
                    _ctx[_k] = _fio_disp(str(_ctx[_k]))
                if example_map.get(_k):
                    example_map[_k] = _fio_disp(str(example_map[_k]))
                if default_values.get(_k):
                    default_values[_k] = _fio_disp(str(default_values[_k]))
            _auto = build_template_values(_ctx, t["code"], _ctx) or {}
        except Exception:
            _auto = {}

        # Значения в окне просмотра приводим ТЕМ ЖЕ нормализатором, что и выпуск
        # документа. Иначе один и тот же документ в HTML-вкладке и в сравнении
        # выглядит по-разному (двойные скобки у суммы прописью, формат суммы).
        _norm = {}
        try:
            _merged = dict(_auto)
            _merged.update({k: v for k, v in default_values.items() if v})
            _merged.update({k: v for k, v in example_map.items() if v})
            _norm = doc_render.normalize(_merged, t["code"]) or {}
        except Exception as _e:
            _norm = {}
            try:
                print("нормализация значений визора не удалась: %r" % (_e,), flush=True)
            except Exception:
                pass

        # Фотография клиента — это <img src>, а не текст: обёртка подсветки сломала бы
        # атрибут (в src попадал <span>). Источник тот же, что у генерации документа —
        # подготовленный кадр клиента; пока кадра нет, показываем заглушку-аватарку
        # размером с поле фотографии.
        _photo_url = PHOTO_PLACEHOLDER
        if app_id and app_row:
            try:
                from services.values import _client_photo_path as _cpp
                _pp = _cpp((client or {}).get("id"))
                if _pp and Path(_pp).is_file():
                    _photo_url = f"/applications/{app_id}/client-photo"
            except Exception:
                _photo_url = PHOTO_PLACEHOLDER

        from services import var_methods as _vm
        _meth = _vm.methods_for_template(template_id)

        def _hl(m):
            nm = m.group(1)
            # форма иммиграции (Statement Letter): пустые значения печатаем прочерком
            try:
                _is_form = str((t or {}).get("code") or "").startswith("statement_letter")
            except Exception:
                _is_form = False
            if nm in ("client_photo_url", "client_photo"):
                return _photo_url
            # Порядок источников: нормализованные значения (как при выпуске) → пример → поля → авто.
            val = (_norm.get(nm) or example_map.get(nm) or default_values.get(nm) or _auto.get(nm) or "").strip()
            # ФИО показываем по нашим правилам — с отчеством (в оригинальных примерах его нет)
            if val and nm in ("client_name", "full_name", "full_name_latin", "cv_name",
                              "employee_name", "employee_full_name", "employee_full_name_latin"):
                try:
                    from services.values import fio_full_for_display as _fio_disp
                    val = _fio_disp(val)
                except Exception:
                    pass
            ph = "{{ %s }}" % nm
            if not val:
                # В формах иммиграции (Statement Letter) пустое значение печатаем прочерком:
                # имя переменной в окне просмотра заявки выглядит как брак документа.
                try:
                    _is_form = str((t or {}).get("code") or "").startswith("statement_letter")
                except Exception:
                    _is_form = False
                if _is_form:
                    val = "-"
            # Пустая переменная — пустое место: имя переменной в документе не пишем
            # ни в окне просмотра, ни в PDF (правило заказчика для всех документов).
            # Исключение — формы иммиграции: там по канону бланка ставится прочерк.
            shown = _esc(val) if val else '-' if _is_form else ''
            _cls = 'var-hl' + (' var-dash' if _is_form else '')
            # Цвет переменной = способ её формирования (правило заказчика):
            # зелёный — из документа клиента, оранжевый — собрано логически, красный — случайно.
            try:
                _m = (_meth or {}).get(nm, '')
                _src = _vm.src_kind(_m)
                _cls += ' var-src-' + _src
                _srctxt = _vm.src_ru(_src)
            except Exception:  # noqa: BLE001
                _src, _srctxt = '', ''
            return ('<span class="' + _cls + '" data-var="' + nm + '" data-ph="' + _esc(ph) + '"'
                    + (' data-src="' + _src + '"' if _src else '')
                    + (' title="' + _esc(nm + ' — ' + _srctxt) + '"' if _srctxt else '')
                    + (' data-val="' + _esc(val) + '"' if val else '') + '>' + shown + '</span>')

        html_render = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", _hl, _raw)
        # стили шаблона ограничиваем окном просмотра: иначе они красят всю страницу
        html_render = re.sub(r"<style[^>]*>(.*?)</style>",
                              lambda m: "<style>" + _scope_css(m.group(1)) + "</style>",
                              html_render, flags=re.S)
    else:
        html_render = '<span class="muted">HTML не сконвертирован. <a href="/templates/' + str(template_id) + '">Конвертировать PDF → HTML</a></span>'

    pv_js_html = "<script>(function(){var ttl=document.getElementById('pv-title');var modes=document.querySelectorAll('.js-docmode');Array.prototype.forEach.call(modes,function(b){b.addEventListener('click',function(){var t=document.getElementById('pv-title'); if(!t) return;var name=(b.textContent||'').replace(/[^A-Za-zА-Яа-я0-9\\- ]/g,'').trim();t.textContent='Окно просмотра (визор)';});});})();(function(){var b=document.getElementById('var-marks-btn');if(b){b.addEventListener('click',function(){document.body.classList.toggle('show-varnames');b.classList.toggle('is-on',document.body.classList.contains('show-varnames'));});}var rows=document.querySelectorAll('.var-row');Array.prototype.forEach.call(rows,function(r){var info=r.querySelector('.var-info');var line=r.querySelector('.var-line');if(!info||!line)return;var ttl=info.getAttribute('title')||info.getAttribute('data-tip')||'';if(!ttl)return;var m1=ttl.match(/Тип:\\s*([^\\n]+)/);var m2=ttl.match(/Откуда берётся:\\s*([^\\n]+)/);if(!m1&&!m2)return;var hint=document.createElement('span');hint.className='var-rule-hint';var cls=(m1&&m1[1].indexOf('—')>0)?m1[1].split('—')[0].trim():'';var src=m2?m2[1].trim():'';var bb=document.createElement('b');bb.textContent=cls;if(cls){hint.appendChild(bb);}if(cls&&src){hint.appendChild(document.createTextNode(' · '));}hint.appendChild(document.createTextNode(src));line.appendChild(hint);});})();</script>"

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
        ".cv-pieces-modal{position:fixed;inset:0;z-index:4200;background:rgba(15,38,27,.5);display:flex;"
        "align-items:center;justify-content:center;padding:16px;}"
        ".cv-pieces-box{background:#fff;border-radius:12px;max-width:760px;width:100%;max-height:86vh;overflow:auto;padding:16px;}"
        ".cv-pieces-list{display:flex;flex-direction:column;gap:6px;margin:10px 0;}"
        ".cv-pieces-list label{display:flex;gap:8px;align-items:flex-start;font-size:13px;line-height:1.35;"
        "padding:6px 8px;border:1px solid #E3EAE5;border-radius:8px;cursor:pointer;}"
        ".cv-pieces-list .cv-en{display:block;font-size:11px;color:#6B7C70;margin-top:2px;}"
        ".cv-pieces-foot{display:flex;gap:8px;justify-content:flex-end;margin-top:8px;}"
        ".cv-pieces-foot button{padding:7px 14px;border-radius:8px;border:1px solid #C9D6CE;background:#fff;cursor:pointer;font-weight:600;}"
        ".cv-pieces-foot .cv-ok{background:#1D4ED8;color:#fff;border-color:#1D4ED8;}"
        "</style>"
        "<script>(function(){"
        "var CV_VARS=['cv_summary','cv_job1_bullets','cv_job2_bullets','cv_job3_bullets','cv_skills_hard','cv_skills_soft','cv_skills_tools'];"
        "var TPL=(location.pathname.match(/\\/templates\\/(\\d+)/)||[])[1]||'';"
        "if(!TPL) return;"
        "function fieldOf(n){return document.querySelector('input[data-var=\"'+n+'\"], textarea[data-var=\"'+n+'\"]');}"
        "function openPieces(f,pairs,name){"
        "  var isProse=/summary|profile/i.test(name);"
        "  var box=document.createElement('div');box.className='cv-pieces-modal';"
        "  var rows=pairs.map(function(p,i){"
        "    var ru=String((p&&(p.ru||p.en))||p).replace(/[<>]/g,'');"
        "    var en=String((p&&p.en)||p).replace(/[<>]/g,'');"
        "    return '<label><input type=\"checkbox\" value=\"'+i+'\"> <span>'+ru+'</span>'"
        "      +(en&&en!==ru?'<span class=\"cv-en\">'+en+'</span>':'')+'</label>';}).join('');"
        "  box.innerHTML='<div class=\"cv-pieces-box\"><b>Готовые предложения — отметьте нужные</b>'"
        "   +'<div class=\"cv-pieces-list\">'+rows+'</div>'"
        "   +'<div class=\"cv-pieces-foot\"><button type=\"button\" class=\"cv-cancel\">Отмена</button>'"
        "   +'<button type=\"button\" class=\"cv-ok\">Подставить выбранные</button></div></div>';"
        "  document.body.appendChild(box);"
        "  box.querySelector('.cv-cancel').addEventListener('click',function(){box.remove();});"
        "  box.addEventListener('click',function(e){if(e.target===box)box.remove();});"
        "  box.querySelector('.cv-ok').addEventListener('click',function(){"
        "    var picked=Array.prototype.slice.call(box.querySelectorAll('input:checked'))"
        "      .map(function(c){var p=pairs[parseInt(c.value,10)];return (p&&p.en)||p;});"
        "    if(!picked.length){box.remove();return;}"
        "    var text=picked.map(function(s){return String(s).replace(/^[\\u2022\\-\\s]+/,'').trim();}).join(isProse?' ':'\\n');"
        "    if(isProse&&text&&!/[.!?]$/.test(text)) text+='.';"
        "    f.value=text;f.dispatchEvent(new Event('input',{bubbles:true}));box.remove();"
        "  });"
        "}"
        "var PROF_CODES={};"
        "fetch('/templates/'+TPL+'/cv/professions',{headers:{'X-Requested-With':'fetch'}})"
        "  .then(function(r){return r.json();}).then(function(d){"
        "    (d.items||[]).forEach(function(p){PROF_CODES[p.code]=p.en||p.ru;});"
        "  }).catch(function(){});"
        "function profCode(){"
        "  var pf=fieldOf('cv_profession');var v=pf?String(pf.value||'').trim():'';"
        "  if(!v)return '';"
        "  if(PROF_CODES[v])return v;"
        "  for(var k in PROF_CODES){if(String(PROF_CODES[k]).toUpperCase()===v.toUpperCase())return k;}"
        "  return '';}"
        "function setField(n,v){var el=fieldOf(n);if(el){el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));}return !!el;}"
        "function panelFor(name){"
        "  var f=fieldOf(name); if(!f) return;"
        "  if(f.parentNode.querySelector('.cv-gen-panel')) return;"
        "  var row=f.closest('.var-row')||f.parentNode;"
        "  var m=/^cv_job(\\d+)_(\\w+)$/.exec(name); var what=m?m[2]:'';"
        "  var h='';"
        "  if(name==='cv_profession'){"
        "    h+='<select class=\\\"cv-prof\\\"><option value=\\\"\\\">профессия из списка…</option></select>';"
        "    h+='<button type=\\\"button\\\" class=\\\"cv-exp\\\" title=\\\"Подобрать 2–3 места: должности, компании, даты и обязанности\\\">🧩 Подобрать опыт</button>';"
        "  } else if(what==='title'){"
        "    h+='<select class=\\\"cv-job-title\\\"><option value=\\\"\\\">должность…</option></select>';"
        "    h+='<span class=\\\"cv-note\\\">из документов клиента или из списка</span>';"
        "  } else if(what==='company'){"
        "    h+='<select class=\\\"cv-job-comp\\\"><option value=\\\"\\\">организация…</option></select>';"
        "  } else if(what==='period'){"
        "    h+='<button type=\\\"button\\\" class=\\\"cv-dates\\\" title=\\\"Даты по календарю: назад без пересечений\\\">📅 Даты</button>';"
        "  } else if(name==='cv_education_school'){"
        "    h+='<select class=\\\"cv-uni\\\"><option value=\\\"\\\">учебное заведение…</option></select>';"
        "    h+='<span class=\\\"cv-note\\\"></span>';"
        "  } else if(name==='cv_education_degree'){"
        "    h+='<select class=\\\"cv-deg\\\"><option value=\\\"\\\">образование из списка…</option></select>';"
        "  } else if(what==='bullets'||name==='cv_summary'){"
        "    h+='<button type=\\\"button\\\" class=\\\"cv-dice\\\" title=\\\"Пересобрать описание из кусочков\\\">🎲 Кубик</button>';"
        "    h+='<button type=\\\"button\\\" class=\\\"cv-pieces\\\" title=\\\"Отметить готовые предложения\\\">＋ Кусочки</button>';"
        "    if(what==='bullets')h+='<button type=\\\"button\\\" class=\\\"cv-more\\\" title=\\\"Добавить ещё одно место работы\\\">＋ Ещё место</button>';"
        "  }"
        "  h+='<span class=\\\"cv-hint\\\"></span>';"
        "  if(!h)return;"
        "  var box=document.createElement('div');box.className='cv-gen-panel';box.innerHTML=h;"
        "  row.parentNode.insertBefore(box,row.nextSibling);"
        "  function hint(t){box.querySelector('.cv-hint').textContent=t||'';}"
        "  function put(txt,msg){f.value=txt;f.dispatchEvent(new Event('input',{bubbles:true}));hint(msg);}"
        "  function prefix(){return m?('cv_job'+m[1]+'_'):'cv_job1_';}"
        "  function expand(){"
        "    var code=profCode(); if(!code){hint('сначала выберите профессию выше');return null;}"
        "    return code;}"
        "  function jobCount(){var mx=2;CV_VARS.forEach(function(v){var mm=/^cv_job(\\d+)_/.exec(v);"
        "    if(mm)mx=Math.max(mx,parseInt(mm[1],10));});return mx;}"
        "  function fillJobSelects(code){"
        "    var jt=box.querySelector('.cv-job-title'),jc=box.querySelector('.cv-job-comp');"
        "    if(!code){return;}"
        "    fetch('/templates/'+TPL+'/cv/jobs?code='+encodeURIComponent(code),{headers:{'X-Requested-With':'fetch'}})"
        "      .then(function(r){return r.json();}).then(function(d){"
        "        if(!d.ok)return;"
        "        if(jt)jt.innerHTML='<option value=\\\"\\\">должность…</option>'+(d.titles||[]).map(function(t){return '<option data-en=\\\"'+t.en+'\\\">'+t.ru+'</option>';}).join('');"
        "        if(jc)jc.innerHTML='<option value=\\\"\\\">организация…</option>'+(d.companies||[]).map(function(c){return '<option data-sector=\\\"'+(c.sector||'')+'\\\">'+c.name+'</option>';}).join('');"
        "      }).catch(function(){});"
        "  }"
        "  function rebuildDuties(){"
        "    var code=profCode(); if(!code)return;"
        "    var jc=box.querySelector('.cv-job-comp');"
        "    var s=(jc&&jc.selectedIndex>0&&jc.options[jc.selectedIndex].dataset.sector)||'';"
        "    fetch('/templates/'+TPL+'/cv/job_duties',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'fetch'},"
        "      body:JSON.stringify({code:code,sector:s,level:'medium'})})"
        "      .then(function(r){return r.json();}).then(function(d){"
        "        if(d.ok&&d.duties&&d.duties.length){"
        "          setField(prefix()+'bullets',d.duties.map(function(x){return x.en;}).join('\\n'));"
        "          hint('описание пересобрано под эту должность и организацию');"
        "        }}).catch(function(){});"
        "  }"
        "  var sel=box.querySelector('.cv-prof');"
        "  if(sel){"
        "    fetch('/templates/'+TPL+'/cv/professions',{headers:{'X-Requested-With':'fetch'}})"
        "      .then(function(r){return r.json();}).then(function(d){"
        "        (d.items||[]).forEach(function(p){var o=document.createElement('option');o.value=p.code;o.textContent=p.ru||p.en;sel.appendChild(o);});"
        "      }).catch(function(){});"
        "    sel.addEventListener('change',function(){"
        "      var o=sel.options[sel.selectedIndex];"
        "      if(o&&o.value){put(o.textContent,'профессия выбрана — «Подобрать опыт» заполнит места работы');}"
        "    });"
        "    var ex=box.querySelector('.cv-exp');"
        "    if(ex)ex.addEventListener('click',function(){"
        "      var code=sel.value; if(!code){hint('выберите профессию из списка');return;}"
        "      put(sel.options[sel.selectedIndex].textContent,'подбираю опыт…');"
        "      fetch('/templates/'+TPL+'/cv/roll_experience',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'fetch'},"
        "        body:JSON.stringify({code:code,level:'medium',count:jobCount()})})"
        "        .then(function(r){return r.json();}).then(function(d){"
        "          if(!d.ok){hint(d.error||'не удалось подобрать');return;}"
        "          (d.items||[]).forEach(function(it,i){"
        "            var p='cv_job'+(i+1)+'_';"
        "            setField(p+'title',it.title);setField(p+'company',it.company);"
        "            setField(p+'period',it.period);"
        "            setField(p+'bullets',(it.duties||[]).join('\\n'));"
        "          });"
        "          hint('опыт заполнен: '+(d.items||[]).length+' места работы');"
        "        }).catch(function(e){hint('сетевая ошибка: '+e);});"
        "    });"
        "  }"
        "  var jt=box.querySelector('.cv-job-title'),jc=box.querySelector('.cv-job-comp');"
        "  fillJobSelects(profCode());"
        "  if(jt)jt.addEventListener('change',function(){"
        "    var o=jt.options[jt.selectedIndex];"
        "    if(o&&o.dataset.en)setField(prefix()+'title',o.dataset.en);"
        "    rebuildDuties();"
        "  });"
        "  if(jc)jc.addEventListener('change',function(){"
        "    var o=jc.options[jc.selectedIndex];"
        "    if(o&&o.value)setField(prefix()+'company',o.textContent);"
        "    rebuildDuties();"
        "  });"
        "  var un=box.querySelector('.cv-uni');"
        "  if(un){"
        "    var pf=fieldOf('cv_place_of_birth');"
        "    var fillUni=function(){"
        "      var city=pf?pf.value:'';"
        "      fetch('/templates/'+TPL+'/cv/universities?city='+encodeURIComponent(city),{headers:{'X-Requested-With':'fetch'}})"
        "        .then(function(r){return r.json();}).then(function(d){"
        "          var note=box.querySelector('.cv-note');"
        "          if(note)note.textContent=d.label?('город: '+d.label):'город не указан — общий список';"
        "          un.innerHTML='<option value=\\\"\\\">учебное заведение…</option>'+(d.items||[]).map(function(u){return '<option>'+u+'</option>';}).join('');"
        "        }).catch(function(){});"
        "    };"
        "    fillUni();"
        "    if(pf)pf.addEventListener('change',fillUni);"
        "    un.addEventListener('change',function(){var o=un.options[un.selectedIndex];"
        "      if(o&&o.value){put(o.textContent,'вуз из пула города места рождения');"
        "        f.dispatchEvent(new Event('change',{bubbles:true}));}});"
        "  }"
        "  var dg=box.querySelector('.cv-deg');"
        "  if(dg){"
        "    var us=fieldOf('cv_education_school');"
        "    var fillDeg=function(){"
        "      var uni=us?us.value:'';"
        "      fetch('/templates/'+TPL+'/cv/majors?university='+encodeURIComponent(uni),{headers:{'X-Requested-With':'fetch'}})"
        "        .then(function(r){return r.json();}).then(function(d){"
        "          dg.innerHTML='<option value=\\\"\\\">образование из списка…</option>'+(d.items||[]).map(function(x){return '<option>'+x+'</option>';}).join('');"
        "        }).catch(function(){});"
        "    };"
        "    fillDeg();"
        "    if(us)us.addEventListener('change',fillDeg);"
        "    dg.addEventListener('change',function(){var o=dg.options[dg.selectedIndex];"
        "      if(o&&o.value)put(o.textContent,'специальность по выбранному вузу');});"
        "  }"
        "  var bt=box.querySelector('.cv-dates');"
        "  if(bt)bt.addEventListener('click',function(){"
        "    var code=expand(); if(!code)return;"
        "    fetch('/templates/'+TPL+'/cv/roll_experience',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'fetch'},"
        "      body:JSON.stringify({code:code,level:'medium',count:jobCount()})})"
        "      .then(function(r){return r.json();}).then(function(d){"
        "        if(!d.ok){hint(d.error||'');return;}"
        "        (d.items||[]).forEach(function(it,i){setField('cv_job'+(i+1)+'_period',it.period);});"
        "        hint('даты расставлены назад по календарю, без пересечений');"
        "      }).catch(function(e){hint('сетевая ошибка: '+e);});"
        "  });"
        "  var dz=box.querySelector('.cv-dice');"
        "  if(dz)dz.addEventListener('click',function(){"
        "    var code=expand(); if(!code)return;"
        "    dz.disabled=true;hint('собираю описание из кусочков…');"
        "    fetch('/templates/'+TPL+'/cv/random',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'fetch'},"
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
        "    var jt='';var _m=/^cv_job([0-9]+)_bullets$/.exec(name);"
        "    if(_m){var _tf=fieldOf('cv_job'+_m[1]+'_title'); jt=_tf?String(_tf.value||'').trim():'';}"
        "    fetch('/templates/'+TPL+'/cv/phrases?code='+encodeURIComponent(code)+'&job='+encodeURIComponent(jt)+'&var='+encodeURIComponent(name),{headers:{'X-Requested-With':'fetch'}})"
        "      .then(function(r){return r.json();}).then(function(d){openPieces(f,(d.pairs||[]).length?d.pairs:(d.items||[]).map(function(s){return {en:s,ru:s};}),name);})"
        "      .catch(function(e){alert('сетевая ошибка: '+e);});"
        "  });"
        "  var mr=box.querySelector('.cv-more');"
        "  if(mr)mr.addEventListener('click',function(){"
        "    mr.disabled=true;hint('добавляю ещё одно место работы…');"
        "    fetch('/templates/'+TPL+'/cv/add_job',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'fetch'},body:'{}'})"
        "      .then(function(r){return r.json();}).then(function(d){"
        "        if(d.ok){location.reload();}else{mr.disabled=false;hint('не удалось добавить место');}"
        "      }).catch(function(e){mr.disabled=false;alert('сетевая ошибка: '+e);});"
        "  });"
        "}"
        "function addAll(){CV_VARS.forEach(panelFor);}"
        "if(document.readyState==='complete') addAll(); else window.addEventListener('load',addAll);"
        "var aj=document.querySelector('.cv-add-job');"
        "if(aj)aj.addEventListener('click',function(){"
        "  aj.disabled=true;var t0=aj.textContent;aj.textContent='добавляю…';"
        "  fetch('/templates/'+TPL+'/cv/add_job',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'fetch'},body:'{}'})"
        "    .then(function(r){return r.json();}).then(function(d){"
        "      if(d.ok){location.reload();}else{aj.disabled=false;aj.textContent=t0;}})"
        "    .catch(function(){aj.disabled=false;aj.textContent=t0;});});"
        "})();</script>")
    pdf_modal_html = '\n<style>\n.tpl-pdf-btn { margin-left:8px; background:linear-gradient(135deg,#3B82F6,#1D4ED8 62%,#1E40AF); color:#fff; border:0; border-radius:7px;\n               width:150px; height:26px; padding:0; font-size:11.5px; line-height:1; font-weight:800; letter-spacing:.01em; cursor:pointer; white-space:nowrap;\n               box-shadow:0 2px 7px rgba(29,78,216,.30), 0 1px 0 rgba(255,255,255,.35) inset;\n               transition:filter .15s ease, box-shadow .15s ease, transform .12s ease; }\n.tpl-pdf-btn:hover { filter:brightness(1.09) saturate(1.06); box-shadow:0 5px 14px rgba(29,78,216,.38); transform:translateY(-1px); }\n.tpl-pdf-btn:active { transform:translateY(0); box-shadow:0 2px 6px rgba(29,78,216,.30); }\n.fill-flag { display:inline-flex; align-items:center; gap:6px; margin-left:auto; padding:5px 10px; font-size:12px; font-weight:600; border-radius:8px; background:#FEF3C7; color:#92400E; border:1px solid #FCD34D; cursor:default; white-space:nowrap; }\n.fill-flag.is-ok { background:#DCFCE7; color:#166534; border-color:#86EFAC; }\n.pdf-warn { background:#DC2626; color:#fff; font-size:13px; font-weight:600; padding:8px 14px; }\n.pdf-warn[hidden] { display:none; }\n.pdf-modal[hidden] { display:none; }\n.pdf-modal { position:fixed; inset:0; z-index:4000; display:flex; align-items:center; justify-content:center; }\n.pdf-modal-back { position:absolute; inset:0; background:rgba(15,38,27,.55); }\n.pdf-modal-box { position:relative; width:96vw; height:94vh; background:#fff; border-radius:12px;\n                 display:flex; flex-direction:column; overflow:hidden; box-shadow:0 20px 60px rgba(0,0,0,.35); }\n.pdf-modal-head { display:flex; align-items:center; gap:10px; padding:10px 14px; border-bottom:1px solid #E1E7E3; }\n.pdf-modal-head b { font-size:14px; }\n.pdf-modal-head .sp { margin-left:auto; display:flex; gap:8px; }\n.pdf-modal-body { flex:1; background:#E7EBEE; position:relative; }\n.pdf-loading { position:absolute; inset:0; background:#fff; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; z-index:6; }\n.pdf-loading[hidden] { display:none; }\n.pdf-spinner { width:54px; height:54px; border:5px solid #DBEAFE; border-top-color:#1D4ED8; border-radius:50%; animation:pdfspin .9s linear infinite; }\n@keyframes pdfspin { to { transform:rotate(360deg); } }\n.pdf-bar { width:min(420px,70vw); height:6px; background:#E5E7EB; border-radius:99px; overflow:hidden; }\n.pdf-bar i { display:block; width:40%; height:100%; background:#1D4ED8; border-radius:99px; animation:pdfbar 1.2s ease-in-out infinite; }\n@keyframes pdfbar { 0%{margin-left:-40%} 100%{margin-left:100%} }\n.pdf-loading-text { font-size:15px; font-weight:600; color:#1F2937; }\n.pdf-loading-hint { font-size:12px; color:#6B7280; }\n.tpl-pdf-btn.is-busy { opacity:.75; cursor:progress; }\n.pdf-modal-body iframe { width:100%; height:100%; border:0; background:#fff; }\n</style>\n<div class="pdf-modal" id="pdf-modal" hidden>\n  <div class="pdf-modal-back" data-pdf-close></div>\n  <div class="pdf-modal-box">\n    <div class="pdf-modal-head">\n      <b>Готовый PDF</b>\n      <span class="muted" id="pdf-modal-note"></span>\n      <span class="sp">\n        <a class="btn sm" id="pdf-modal-dl" href="#" download>💾 Скачать</a>\n        <button class="btn sm ghost" type="button" data-pdf-close>✕ Закрыть</button>\n      </span>\n    </div>\n    <div class="pdf-warn" id="pdf-warn" hidden></div>\n <div class="pdf-modal-body"><div class="pdf-loading" id="pdf-loading" hidden><div class="pdf-spinner"></div><div class="pdf-loading-text" id="pdf-loading-text">Формирую документ…</div><div class="pdf-bar"><i></i></div><div class="pdf-loading-hint">обычно 2–5 секунд</div></div><iframe id="pdf-modal-frame" title="Готовый PDF"></iframe></div></div>\n  </div>\n</div>\n<script>\n(function(){\n  var btn = document.getElementById(\'tpl-pdf-open\');\n  var modal = document.getElementById(\'pdf-modal\');\n  if (!btn || !modal) return;\n  var frame = document.getElementById(\'pdf-modal-frame\');\n  var dl = document.getElementById(\'pdf-modal-dl\');\n  var note = document.getElementById(\'pdf-modal-note\');\n  var loading = document.getElementById(\'pdf-loading\');\n  var loadingText = document.getElementById(\'pdf-loading-text\');\n  var loadTmr = null, loadTick = 0;\n  function showLoading(){\n    if (!loading) return;\n    loadTick = 0; loading.hidden = false;\n    if (loadingText) loadingText.textContent = \'Формирую документ…\';\n    clearInterval(loadTmr);\n    loadTmr = setInterval(function(){ loadTick++; if (loadingText) loadingText.textContent = \'Формирую документ… \' + loadTick + \' с\'; }, 1000);\n    btn.disabled = true; btn.classList.add(\'is-busy\');\n  }\n  function hideLoading(){\n    if (loading) loading.hidden = true;\n    clearInterval(loadTmr);\n    btn.disabled = false; btn.classList.remove(\'is-busy\');\n  }\n  if (frame) frame.addEventListener(\'load\', function(){ if (frame.src && frame.src.indexOf(\'about:blank\') < 0) hideLoading(); });\n  function close(){ modal.hidden = true; if (frame) frame.src = \'about:blank\'; }\n  btn.addEventListener(\'click\', function(){\n    var values = {};\n    document.querySelectorAll(\'input[data-var]\').forEach(function(i){ values[i.getAttribute(\'data-var\')] = i.value; });\n    document.querySelectorAll(\'#html-stage [data-var]\').forEach(function(sp){\n      var nm = sp.getAttribute(\'data-var\'), v = sp.getAttribute(\'data-val\');\n      if (v && !values[nm]) values[nm] = v;\n    });\n    showLoading();\n    note.textContent = \'формирую PDF…\';\n    modal.hidden = false; frame.src = \'about:blank\';\n    fetch(\'/templates/\' + btn.dataset.template + \'/preview_pdf\', {\n      method:\'POST\', headers:{\'Content-Type\':\'application/json\',\'X-Requested-With\':\'fetch\'},\n      body: JSON.stringify({values: values})\n    }).then(function(r){ return r.json(); }).then(function(j){\n      if (!j.ok) { hideLoading(); note.textContent = j.error || \'не удалось собрать PDF\'; return; }\n      note.textContent = j.name || \'\';\n      var _href = encodeURI(j.url);\n      dl.href = _href; dl.setAttribute(\'download\', j.name || \'document.pdf\');\n      frame.src = _href + \'#zoom=page-fit\';\n      setTimeout(hideLoading, 20000);\n    }).catch(function(e){ hideLoading(); note.textContent = \'ошибка сети: \' + e; });\n  });\n  modal.addEventListener(\'click\', function(e){\n    if (e.target.closest(\'[data-pdf-close]\')) close();\n  });\n  document.addEventListener(\'keydown\', function(e){ if (e.key === \'Escape\' && !modal.hidden) close(); });\n})();\n</script>\n'
    if rendered_pdf_url:
        preview_inner = (
            f'<div class="zp-preview" data-zoom-pan><iframe class="pdf-preview-iframe" style="width:794.5px;height:1123px;border:0" src="{rendered_pdf_url}#zoom=100&toolbar=0"></iframe></div>'
        )
    else:
        preview_inner = (
            '<div class="preview-empty">'
            '<div style="font-size:48px;opacity:.4">📄</div>'
            '<div>После нажатия «Сформировать»<br>здесь появится готовый PDF</div>'
            '</div>'
        )

    # --- Две кнопки просмотра: HTML-шаблон и размеченный оригинал (пример из Google Drive) ---
    # --- Две вкладки над окном просмотра: размеченный оригинал и HTML-шаблон ---
    _orig_btn = ""
    _tpl_dir = f"/opt/wolf_v2/data/templates/{t['code']}"
    _clean_path = f"{_tpl_dir}/example_filled.pdf"      # настоящий заполненный документ клиента
    _marked_path = f"{_tpl_dir}/example_marked.pdf"     # тот же документ с разметкой переменных
    # Кнопку «Оригинальный пример» показываем только там, где образец реально есть,
    # и ведём на чистый заполненный документ (разметка — запасной вариант).
    _cli_src = _client_original_path(t["code"], int((client or {}).get("id") or 0)) if client else None
    if _cli_src:
        # У этого клиента документ нужного типа уже есть — показываем именно его,
        # а не чужой образец (требование Андрея, 06.10.2026).
        _orig_btn = (f'<button type="button" class="doc-tab js-docmode" role="tab" '
                     f'data-pdfview="/templates/pdfview/{template_id}?kind=client{client["id"]}" '
                     f'title="Реальный документ этого клиента: {os.path.basename(_cli_src)}">'
                     f'Оригинал</button>')
    elif os.path.exists(_clean_path) or os.path.exists(_marked_path):
        _kind = "clean" if os.path.exists(_clean_path) else "marked"
        _orig_btn = (f'<button type="button" class="doc-tab js-docmode" role="tab" '
                     f'data-pdfview="/templates/pdfview/{template_id}?kind={_kind}" '
                     f'title="Заполненный документ клиента, как он выглядит на самом деле">Оригинал</button>')
    else:
        _orig_btn = ''
    # Кнопка предпросмотра PDF стоит на одной горизонтали с вкладками, справа от них
    _pdf_btn = (f'<button type="button" class="tpl-pdf-btn" id="tpl-pdf-open" data-template="{template_id}" '
                f'title="Открыть просмотр сформированного PDF">🔍 Просмотр PDF</button>')
    # Правая часть строки вкладок: пара «Оригинал / Перевод» и кнопка предпросмотра PDF.
    # Ширина пары равна ширине кнопки PDF (задаётся в CSS), отступы сверху и снизу одинаковые.
    # Пара «Оригинал / Перевод» — переехала из тулбара в строку вкладок (слово «Язык» убрано)
    lang_sw = ('<span class="lang-switch" id="lang-switch">'
               '<button type="button" class="ls-btn is-on" data-lang="orig">🇬🇧 Оригинал</button>'
               '<button type="button" class="ls-btn" data-lang="ru">🇷🇺 Перевод</button>'
               '</span>')
    # Ширина пары равна ширине кнопки PDF (задаётся в CSS), отступы сверху и снизу одинаковые.
    _ls_note = ('<span class="ls-note" id="ls-note" role="status" aria-live="polite"></span>')
    # Сравнение открывается поверх страницы (модальный слой), без новой вкладки браузера.
    # Доступно и в конструкторе документов (без заявки), и в заявке (Андрей, 16.10.2026):
    # слева — оригинал, справа — наш документ, собранный тем движком, что закреплён за шаблоном.
    _cmp_title = ("Документ №%s — %s" % ((t or {}).get("doc_index") or template_id,
                                         (t or {}).get("title") or "")
                  ).replace("&", "&amp;").replace("<", "&lt;")
    _cmp_btn = ""
    cmp_modal_html = ""
    if True:
        _cmp_url = (f'/templates/compare/{template_id}?embed=1&product={_product_id or ""}'
                    + (f'&app={app_id}' if app_id else ''))
        _cmp_btn = (f'<button type="button" class="doc-tab" id="cmp-open" data-cmp="{_cmp_url}" '
                    f'data-cmp-note="{_cmp_ctx_esc}" '
                    f'title="Открыть поверх окна: слева оригинал клиента, справа сборка системы">'
                    f'Сравнение</button>')
        cmp_modal_html = (
            '<style>'
            '.cmp-modal[hidden]{display:none}'
            '.cmp-modal{position:fixed;inset:0;z-index:4100;display:flex;align-items:center;'
            'justify-content:center}'
            '.cmp-modal-back{position:absolute;inset:0;background:rgba(15,38,27,.55)}'
            '.cmp-modal-box{position:relative;width:97vw;height:94vh;background:#fff;border-radius:12px;'
            'display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.35)}'
            '.cmp-modal-head{display:flex;align-items:center;gap:10px;padding:10px 14px;'
            'border-bottom:1px solid #E1E7E3}'
            '.cmp-modal-head b{font-size:14px}.cmp-modal-head .sp{margin-left:auto;display:flex;gap:8px}'
            '.cmp-modal-body{flex:1;background:#E7EBEE}'
            '.cmp-modal-body iframe{width:100%;height:100%;border:0;background:#E7EBEE;display:block}'
            '</style>'
            '<div class="cmp-modal" id="cmp-modal" hidden>'
            '<div class="cmp-modal-back" data-cmp-close></div>'
            '<div class="cmp-modal-box">'
            '<div class="cmp-modal-head"><b>' + _cmp_title + '</b>'
            '<span class="muted" id="cmp-modal-note"></span>'
            '<span class="sp"><button class="btn sm ghost" type="button" data-cmp-close>✕ Закрыть</button></span>'
            '</div>'
            '<div class="cmp-modal-body"><iframe id="cmp-modal-frame" title="Сравнение"></iframe></div>'
            '</div></div>'
            '<script>'
            '(function(){'
            'var btn=document.getElementById("cmp-open"),modal=document.getElementById("cmp-modal");'
            'if(!btn||!modal)return;'
            'var frame=document.getElementById("cmp-modal-frame");'
            'function open(){modal.hidden=false;'
            'var n=document.getElementById("cmp-modal-note");'
            'if(n)n.textContent=btn.getAttribute("data-cmp-note")||"";'
            'if(frame)frame.src=btn.getAttribute("data-cmp");}'
            'function close(){modal.hidden=true;if(frame)frame.src="about:blank";}'
            'btn.addEventListener("click",function(e){e.preventDefault();open();});'
            'modal.addEventListener("click",function(e){if(e.target.closest("[data-cmp-close]"))close();});'
            'document.addEventListener("keydown",function(e){if(e.key==="Escape"&&!modal.hidden)close();});'
            '})();'
            '</script>')
    # Подпись вкладки = движок документа: Word-шаблон так и называется, HTML-шаблон — HTML (Андрей, 16.10.2026).
    _engine_label = "Word" if str((t or {}).get("engine") or "").lower() == "word" else "HTML"
    mode_btns = ('<div class="doc-tabs" id="doc-tabs" role="tablist">' + _orig_btn + _cmp_btn +
                 '<button type="button" class="doc-tab js-docmode is-on" role="tab" data-mode="html" '
                 'title="Наш документ: смотри, как он выйдет с подставленными значениями">'
                 + _engine_label + '</button>'
                 + _pdf_btn + '</div>')

    # В полноэкранном просмотре PDF — те же две кнопки, слева от «Скачать»:
    # зелёная галочка «Сохранить» и красный крестик «Не нужен» (заявка #76).
    if app_id:
        try:
            _pv_st = (db.q1("SELECT status FROM application_documents WHERE application_id=? "
                            "AND template_id=?", (app_id, template_id)) or {}).get("status") or ""
        except Exception:
            _pv_st = ""
        pdf_modal_html = pdf_modal_html.replace(
            '<span class="sp">',
            '<span class="sp">'
            '<button type="button" class="btn sm pdf-vbtn rv-mark%s" data-tpl="%s" data-verdict="verify"'
            ' title="Документ проверен — сохраняем и готовим к отправке">✓ Сохранить</button>'
            '<button type="button" class="btn sm pdf-vbtn rv-mark%s" data-tpl="%s" data-verdict="reject"'
            ' title="Документ не нужен в этой заявке">✕ Не нужен</button>'
            % (" is-on" if _pv_st == "verified" else "", template_id,
               " is-on" if _pv_st == "rejected" else "", template_id), 1)

    # правила номеров этого документа (у Сбербанка они свои) — их читает кубик при генерации
    from services.values import number_pattern as _num_pattern
    _num_rule = {_nm: _pt for _nm in ("doc_no", "ref_no") if (_pt := _num_pattern(t.get("code") or "", _nm))}
    data_tools = (
        # Видимой части у этого блока нет: полосу «подставлено полей: N (можно править)» убрали.
        # Внутри остались только служебные данные — пример значений и правила номеров.
        '<div class="ex-tools" data-autofill="' + ('0' if app_id else '1') + '" hidden>'
        '<script id="ex-data" type="application/json">' + json.dumps(example_source, ensure_ascii=False) + '</script>'
            # правила номеров этого документа — их читает кнопка-кубик при генерации
            + '<script id="num-rule" type="application/json">' + json.dumps(_num_rule, ensure_ascii=False) + '</script>'
        '</div>')

    if src_url:
        # Полоса «Данные» из шапки убрана — вместо неё ничего не рендерим,
        # служебный блок со значениями примера уходит в разметку отдельно.
        toolbar_html = data_tools
    else:
        toolbar_html = ('<div class="doc-toolbar"><div class="tb-row">'
                        '<span class="tb-label">Просмотр</span>'
                        '<span class="muted">PDF-эталон не загружен — загрузите его через «+ Загрузить PDF-шаблон»</span>'
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
            f'<span>📊 {len(variables)} переменных</span>'
            f'<span>📑 {t["pages"] or 0} стр.</span>'
            f'<span class="tpl-badge tpl-badge-ok">сверка: совпадает</span>'
            f'<span class="tpl-badge tpl-badge-amber">LLM: {len(variables)}/{len(variables)}</span>'
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
            for _r in db.q("SELECT template_id, status, error FROM application_documents "
                           "WHERE application_id=?", (app_id,)) or []:
                _doc_st[int(_r.get("template_id") or 0)] = _r.get("status") or ""
                _doc_err[int(_r.get("template_id") or 0)] = _r.get("error") or ""
        except Exception:
            _doc_st = {}
            _doc_err = {}
    # В заявке показываем только документы, которые нужны её продукту (Виза C1 → свой
    # набор из product_documents); в конструкторе шаблонов — все документы базы.
    _doc_rows = None
    _pid_for_rail = _product_id or (app_row or {}).get("product_id")
    if _pid_for_rail:
        try:
            _doc_rows = db.q("SELECT t.id, t.title, t.code, t.doc_index FROM templates t "
                             "JOIN product_documents pd ON pd.template_id=t.id "
                             "WHERE pd.product_id=? "
                             "AND COALESCE(t.status,'ok') NOT IN ('merged','hidden') "
                             "ORDER BY pd.sort_order, COALESCE(t.doc_index, 999), t.title",
                             (_pid_for_rail,))
        except Exception:
            _doc_rows = None
    if not _doc_rows:
        _doc_rows = db.q("SELECT id, title, code, doc_index FROM templates "
                         "WHERE COALESCE(status,'ok') NOT IN ('merged','hidden') "
                         "ORDER BY COALESCE(doc_index, 999), title")
    if app_id:
        _ids = {int(_r["id"]) for _r in _doc_rows}
        if int(template_id) not in _ids:      # открытый документ всегда в списке
            _cur = db.q1("SELECT id, title, code, doc_index FROM templates WHERE id=?",
                         (template_id,))
            if _cur:
                _doc_rows = [_cur] + list(_doc_rows)
    # Порядок в столбике: нужные документы — по номеру (возрастание вниз), исключённые
    # крестиком уезжают в конец списка и возвращаются на свою позицию, когда крестик снят.
    try:
        def _ord(r):
            _st = str(_doc_st.get(int(r["id"])) or "")
            try:
                _idx = int(r.get("doc_index") or 999)
            except Exception:
                _idx = 999
            return (1 if _st == "rejected" else 0, _idx, str(r.get("title") or ""))
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
        _num = _tr.get("doc_index") or _tr["id"]
        _target = (f'/applications/{app_id}/review?tpl={_tr["id"]}' if (_embed and app_id)
                   else (f'/templates/{_tr["id"]}?app={app_id}' if app_id
                         else (f'/templates/product/{_product_id}/constructor?tpl={_tr["id"]}'
                               if _product_id else f'/templates/{_tr["id"]}')))
        _marks = ""
        if app_id:
            _st = _doc_st.get(int(_tr["id"]), "")
            _marks = (
                '<span class="tpl-marks">'
                '<button type="button" class="rv-mark tpl-mark%s" data-tpl="%s" data-verdict="verify"'
                ' title="Документ проверен — готовим к отправке">✓</button>'
                '<button type="button" class="rv-mark tpl-mark%s" data-tpl="%s" data-verdict="reject"'
                ' title="Документ не нужен в этой заявке">✕</button>'
                '</span>'
                % (" is-on" if _st == "verified" else "", _tr["id"],
                   " is-on" if _st == "rejected" else "", _tr["id"]))
        # Документ, исключённый правилом (адрес клиента вне зоны офиса), остаётся
        # на полке: затемнён, перечёркнут красным крестом, с причиной под названием.
        _st_row = _doc_st.get(int(_tr["id"]), "")
        _off = (_st_row == "rejected")
        _ok = (_st_row in ("verified", "sent"))
        _why = _doc_err.get(int(_tr["id"]), "") or ""
        # Отсечка по банку клиента: справку делаем только для ЕГО банка (Т-Банк или Сбер),
        # оба сразу не нужны — иначе в пакете лишний документ (правило Андрея, 06.10.2026).
        _cb = str((client or {}).get("bank_name") or "").strip().lower()
        _tcode = str(_tr.get("code") or "").lower()
        if _cb and "bank" in _tcode:
            if "tbank" in _tcode or "tinkoff" in _tcode:
                if "sber" in _cb or "сбер" in _cb:
                    _off, _why = True, "у клиента Сбербанк"
            elif "sber" in _tcode and "sber" not in _cb and "сбер" not in _cb:
                _off = True
                _why = "у клиента " + (str((client or {}).get("bank_name") or "").strip() or "другой банк")
        rail_rows.append(
            '<div class="tpl-mini-wrap">'
            f'<a class="tpl-mini{_on}{" is-off" if _off else ""}{" is-ok" if _ok else ""}{" is-locked" if _off else ""}" '
            f'data-tpl="{_tr["id"]}" data-num="{_num}" '
            + ("" if _off else f'href="{_target}" ')
            + f'title="{_html_mod.escape(str(_tr.get("title") or "") + ((" — " + _why) if _why else ""), quote=True)}">'
            f'<span class="tpl-mini-num">№{_num}</span>'
            f'<img src="/templates/{_tr["id"]}/thumb?v=5'
            + (f'&app={app_id}' if app_id else '') + '" alt="" loading="lazy">'
            + ('<span class="tpl-mini-x">✕</span>' if _off else
               ('<span class="tpl-mini-ok">✓</span>' if _ok else ''))
            + f'<span class="tpl-mini-name">{_html_mod.escape(str(_tr.get("title") or ""))}</span>'
            + (f'<span class="tpl-mini-why">{_html_mod.escape(_why)}</span>'
               if (_off and _why) else '')
            + '</a>'
            + _marks + '</div>')
    rail_html = "".join(rail_rows) or '<div class="tpl-rail-empty">документов нет</div>'

    # ── Вкладка «Клиент»: документы клиента, скачанные с Google Диска ──────────
    # Это те же файлы, что показывает заявка: миниатюры открываются в новой вкладке.
    client_rail = ('<div class="tpl-rail-empty"><div style="font-size:22px;line-height:1;margin-bottom:6px">📥</div>'
                   'Документы клиента появятся здесь, когда конструктор откроется внутри заявки.</div>')
    if app_id and client:
        try:
            from urllib.parse import quote as _q
            from blocks.review.page import _client_files as _cf
            _cfiles = _cf((app_row or {}).get("client_id")) or []
            # «.photo.jpg» — техническая копия кадра для предпросмотра: показываем
            # сам файл, а не его пару (иначе одно фото видно дважды).
            _names = {str(f.get("name")) for f in _cfiles}
            _cfiles = [f for f in _cfiles
                       if not (".photo." in str(f.get("name"))
                               and str(f.get("name")).replace(".photo.", ".") in _names)]
            # Наши документы, сделанные менеджером для этого клиента (E-02, письма, договоры,
            # резюме), во вкладке «Клиент» не показываем: это наши документы, они стоят
            # в полоске «Наши документы» (Андрей, 06.10.2026).
            _cfiles = [f for f in _cfiles if not _manager_kind(str(f.get("name") or ""))]
            _rows = []
            for _f in _cfiles:
                _nm = str(_f.get("name") or "")
                _ext = (_f.get("ext") or "").lower()
                _url = f'/applications/{app_id}/file?name={_q(_nm)}'
                # Миниатюра — лёгкая копия с сервера (картинка или первая страница
                # PDF): сырые файлы клиента весят сотни килобайт, плитке столько
                # не нужно, а PDF браузер в плитке вообще не показывает — раньше
                # вместо миниатюры стоял значок «PDF» (замечание по ИТК в заявке 87).
                _thumb = f'/applications/{app_id}/file-thumb?name={_q(_nm)}'
                if _ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf", ".heic", ".heif"):
                    _inner = f'<img src="{_thumb}" alt="" loading="lazy">'
                else:
                    _inner = f'<span class="tpl-mini-doc">{( _ext.lstrip(".") or "файл").upper()}</span>'
                _rows.append(f'<a class="tpl-mini" href="{_url}" data-client-file="1" '
                             f'data-url="{_url}" data-name="{_html_mod.escape(_nm, quote=True)}" '
                             f'title="{_html_mod.escape(_nm, quote=True)}">{_inner}'
                             f'<span class="tpl-mini-name">{_html_mod.escape(_nm)}</span></a>')
            if _rows:
                client_rail = "".join(_rows)
            else:
                client_rail = ('<div class="tpl-rail-empty">Документы клиента ещё не скачаны — '
                               'нажмите «Разобрать документы» в шапке заявки</div>')
        except Exception as _e:
            client_rail = ('<div class="tpl-rail-empty">Не удалось прочитать документы клиента: '
                           + _html_mod.escape(str(_e)[:120]) + '</div>')
    elif _product_id:
        # Конструктор продукта без заявки: показываем реальные документы клиентов с Google
        # Диска — те, из которых система берёт значения. По одному примеру на тип документа.
        try:
            from urllib.parse import quote as _q
            _kinds = [
                ("Загранпаспорт", re.compile(r"pas+port|paspor|паспорт", re.I)),
                ("Фотография", re.compile(r"photo|foto|фото", re.I)),
                ("Справка банка", re.compile(r"bank|statement|выписка|движени", re.I)),
                ("KITAS / ITK", re.compile(r"\bitk\b|kitas|китас", re.I)),
                ("Адрес / личные данные", re.compile(r"personal|адрес|address|справка", re.I)),
                ("Контракт", re.compile(r"agreement|contract|контракт", re.I)),
            ]
            _cache = BASE_DIR / "data" / "gdrive_cache"
            _apps = db.q("SELECT id, client_id FROM applications WHERE product_id=? "
                         "ORDER BY id DESC LIMIT 40", (_product_id,)) or []
            # Оставляем только те типы документов, которые нужны этому продукту по матрице
            # пакета (C1 → паспорт, фото, адрес, справка банка; контракт и ITK не показываем).
            _allow = None
            try:
                import json as _json
                _m = _json.loads((BASE_DIR / "data" / "guide" / "client_docs_matrix.json")
                                 .read_text(encoding="utf-8"))
                _pcode = ((_prod or {}).get("code") or "")
                _names = " ".join([str(x) for x in (_m.get("minimum") or [])]
                                  + list(((_m.get("products") or {}).get(_pcode, {})
                                          .get("documents") or {}).keys())).lower()
                _rules = (
                    ("Загранпаспорт", ("паспорт", "passport")),
                    ("Фотография", ("фотограф", "photo")),
                    ("Справка банка", ("банк", "bank", "statement")),
                    ("KITAS / ITK", ("kitas", "itk", "китас")),
                    ("Адрес / личные данные", ("адрес", "address", "personal")),
                    ("Контракт", ("контракт", "agreement", "work agreement")),
                )
                _allow = {k for k, keys in _rules if any(w in _names for w in keys)}
            except Exception:  # noqa: BLE001
                _allow = None
            _found, _rows = set(), []
            for _kname, _rx in _kinds:
                if _allow is not None and _kname not in _allow:
                    continue           # этот тип документов продукту не нужен
                for _a in _apps:
                    if _kname in _found:
                        break
                    _cid = _a["client_id"]
                    _fol = _cache / ("client_%s" % _cid)
                    if not _fol.exists():
                        continue
                    _cl = db.client_get(_cid) or {}
                    _fio = ("%s %s" % (_cl.get("surname") or "", _cl.get("name") or "")).strip() \
                        or ("клиент %s" % _cid)
                    for _f in sorted(_fol.iterdir()):
                        if not _f.is_file() or _f.suffix.lower() not in (
                                ".pdf", ".jpg", ".jpeg", ".png", ".webp"):
                            continue
                        if not _rx.search(_f.name):
                            continue
                        if _f.name.lower().startswith("_"):
                            continue
                        if _manager_kind(_f.name):
                            continue      # наш документ (сделан менеджером), не клиентский
                        _url = f'/templates/gdrive/{_cid}/file?name={_q(_f.name)}'
                        _thumb = f'/templates/gdrive/{_cid}/thumb?name={_q(_f.name)}'
                        _rows.append(
                            f'<a class="tpl-mini" href="{_url}" '
                            f'data-client-file="1" data-url="{_url}" '
                            f'data-name="{_html_mod.escape(_f.name, quote=True)}" '
                            f'title="{_html_mod.escape(_f.name, quote=True)}">'
                            f'<img src="{_thumb}" alt="" loading="lazy">'
                            f'<span class="tpl-mini-name">{_html_mod.escape(_kname)}'
                            f'<span class="tpl-mini-why">{_html_mod.escape(_fio)}</span>'
                            f'</span></a>')
                        _found.add(_kname)
                        break
            if _rows:
                client_rail = ("".join(_rows)
                               + '<div class="tpl-rail-note">Реальные документы клиентов '
                                 'с Google Диска — из них система берёт значения.</div>')
            else:
                client_rail = ('<div class="tpl-rail-empty"><div style="font-size:22px;line-height:1;'
                               'margin-bottom:6px">📥</div>Реальных примеров пока нет — '
                               'документы клиентов не скачаны с Google Диска</div>')
        except Exception as _e:  # noqa: BLE001
            client_rail = ('<div class="tpl-rail-empty">Не удалось прочитать примеры клиентов: '
                           + _html_mod.escape(str(_e)[:120]) + '</div>')

    body = f"""
<section class="tpl-card" data-app="{app_id or 0}" data-tpl="{template_id}">
  <h1 class="tpl-title">{(f'🛠 Конструктор продукта · ' + SHORT_NAME.get(_prod.get('code'), _prod.get('name') or '')) if _prod else (("✏️ Редактор документа — " + (t["title"] or "")) if app_id else ("📄 Документ №" + str(t.get("doc_index") or template_id) + " — " + (t["title"] or "")))}</h1>
  {f'<div class="tpl-sub">Открыт документ группы: <b>№{t.get("doc_index") or template_id} · {t["title"] or t["code"]}</b></div>' if _prod else ''}
  {('<div class="tpl-crumbs app-mode-bar" style="margin:10px 0 6px">Документ заявки <b>№' + str(app_id) + '</b> · клиент <b>' + ((client.get("surname") or "") + " " + (client.get("name") or "") if app_id else "") + '</b> · <a class="back-to-app" href="/applications/' + str(app_id) + '/review" id="back-to-app">← Вернуться к заявке</a></div>') if app_id else ''}
  <div class="tpl-meta">{meta_row}</div>
  {toolbar_html}

  <section class="tpl-row-main">
    <!-- Первая колонка: миниатюры (пока заглушка — наполнение уточняем) -->
    <aside class="tpl-rail" id="tpl-rail">
      <div class="tpl-rail-head">📎 Документы</div>
      <!-- Как в браузере: «Наши» — шаблоны конструктора, «Оригиналы» — файлы клиента.
           В конструкторе вторая вкладка пока заглушка; в заявке здесь будут миниатюры
           реальных документов клиента. -->
      <div class="rail-tabs" id="rail-tabs" role="tablist">
        <button type="button" class="rail-tab" role="tab" data-rail="orig" title="Документы клиента с Google Диска">Клиент</button>
        <button type="button" class="rail-tab is-on" role="tab" data-rail="ours" title="Наши документы по выбранному продукту">Наши</button>
      </div>
      <div class="tpl-rail-body" id="tpl-rail-body">{rail_html}</div>
      <div class="tpl-rail-body" id="tpl-rail-orig" hidden>{client_rail}</div>
    </aside>

    <div class="tpl-panel is-vars">
      <div class="tpl-panel-head">
        🔧 Переменные
        <span class="tpl-count{' is-ok' if _filled_n >= len(variables) and variables else ' is-bad'}" id="vars-count">(всего {_filled_n}/{len(variables)}{' ок' if variables and _filled_n >= len(variables) else ''})</span>
      </div>
      <!-- Второй уровень шапки переменных — серая заливка с номером и названием документа -->
      <div class="vars-strip" id="vars-strip"><span class="vars-strip-doc">№{t['doc_index'] if t.get('doc_index') else '—'} · {t['title'] or t['code']}</span></div>
      <div class="tpl-panel-body pl-vars">
        <form method="post" action="/templates/{template_id}/save-defaults" id="vars-form" style="margin:0">
        {f'<input type="hidden" name="product_id" value="{_prod["id"]}">' if _prod else ''}
        <div class="kv-table">
          {var_rows_html or '<div class="muted" style="padding:9px 11px">У шаблона нет переменных</div>'}
        </div>
        </form>
      </div>
    </div>

    <div class="tpl-panel">
      <div class="tpl-panel-head">
        <span id="pv-title">Окно просмотра (визор)</span>
        {_ls_note}
        {lang_sw}
      </div>
      {mode_btns}
      <div class="tpl-panel-body pl-html">
        <!-- В окне визора кнопок подтверждения нет: документ подтверждают и снимают
             только на миниатюре (столбик документов) или в просмотре PDF. -->
          <div class="doc-spinner" aria-hidden="true"><i></i></div>
          <div class="zp-preview" data-zoom-pan><div id="html-stage" class="html-stage">{html_render}</div></div>
      </div>
        <script>
(function(){{
    const stage = document.getElementById('html-stage');
  const btn = document.getElementById('btn-make-var');
  const hint = document.getElementById('var-hint');
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
    const suggested = text.toLowerCase().replace(/[^a-z0-9_а-яё]/gi,'_').slice(0,30) || 'new_var';
    const varName = prompt('Имя новой переменной (латиницей, без пробелов):', suggested);
    if (!varName) return;
    fetch('/templates/{template_id}/add-variable', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ name: varName, default_value: text }})
    }}).then(r => r.json()).then(d => {{
      if (d.ok){{
        // заменим выделенный фрагмент на плейсхолдер {{varName}}
        try {{
          const span = document.createElement('span');
          span.className = 'var-hl';
          span.title = '→ {{ ' + varName + ' }}';
          span.textContent = '{{ ' + varName + ' }}';
          lastRange.deleteContents();
          lastRange.insertNode(span);
          hint.innerHTML = '✅ создана <code class="var-hl-inline">'+'{{ '+varName+' }}'+'</code> — добавьте её в форму слева и нажмите «Сформировать»';
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
{pdf_modal_html}{cmp_modal_html}{pv_js_html}{cv_panel_html}
<script>(function(){{
  /* Окно документа растёт по высоте листа (видно весь документ), а блок переменных
     держим в пределах экрана — он остаётся видимым и прокручивается сам. */
  var vb=document.querySelector('.tpl-panel.is-vars'); if(!vb) return;
  function fit(){{
    if(window.innerWidth<=920){{ vb.style.height=''; return; }}
    fitVars();   /* низ панели переменных — на одной линии с низом окна просмотра */
  }}
  fit(); window.addEventListener('resize',fit); setTimeout(fit,300);

  /* Окно просмотра: ширина ровно под лист + 28px, высота под один лист A4.
     Тогда серая обводка одинаковая по кругу (14px), а лишние листы прокручиваются
     внутри окна; между листами — та же серая полоса 14px (зазор #html-stage). */
  function sheets(){{
    var pl=document.querySelector('.pl-html'); if(!pl) return;
    var host=pl.querySelector('.zp-host')||pl.querySelector('[data-zoom-pan]');
    var stage=pl.querySelector('#html-stage'); if(!host||!stage) return;
    var canvas=pl.querySelector('.zp-canvas');
    var first=stage.querySelector('.sheet')||stage;
    var rh=first.getBoundingClientRect().height;
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
    var marks=stage.querySelectorAll(':scope>.sheet-num');
    for(var m=0;m<marks.length;m++) marks[m].remove();
    for(var i=1;i<list2.length;i++){{
      var b=document.createElement('div');
      b.className='sheet-num';
      b.textContent='Лист '+(i+1);
      b.style.top=Math.round(list2[i].offsetTop-19)+'px';   /* offsetTop — нативные координаты листа */
      stage.appendChild(b);
    }}
    /* Низ панели переменных — по той же границе, что и окно просмотра */
    fitVars();
  }}
  /* Панель переменных той же высоты, что колонка окна просмотра; список внутри прокручивается */
  function fitVars(){{
    var vars=document.querySelector('.tpl-row-main .tpl-panel.is-vars');
    var pl=document.querySelector('.pl-html'); if(!vars||!pl) return;
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
    var pl=document.querySelector('.pl-html'); if(!pl) return;
    var host=pl.querySelector('.zp-host')||pl.querySelector('[data-zoom-pan]');
    if(!host) return;
    host.style.setProperty('width','100%','important');
    host.style.setProperty('max-width','100%','important');
    setTimeout(sheets, 260);
  }}
  setTimeout(sheets, 400); setTimeout(sheets, 1200); setTimeout(sheets, 2400);
  window.addEventListener('resize', function(){{ refit(); setTimeout(refit, 700); }});
  (function(){{
    var _pl=document.querySelector('.pl-html'); if(!_pl) return;
    _pl.addEventListener('click', function(ev){{
      /* Пересборку листов делаем только для «вписать»: при «+»/«−» она растягивала
         окно и лист уезжал вправо (документ №3, 04.10.2026). */
      var t=ev.target.closest('[data-zp]'); if(t && t.getAttribute('data-zp')==='fit') setTimeout(sheets, 350);
    }});
  }})();
  window.__sheets = sheets;
  /* Пока окно просмотра меняет высоту — держим низ панели переменных на той же линии */
  (function(){{
    var pl=document.querySelector('.pl-html'); if(!pl) return;
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
a.back-to-app {{ display:inline-block; margin-left:10px; padding:7px 14px; border-radius:9px;
  background:#14663A; color:#fff !important; font-weight:700; font-size:14px; text-decoration:none; }}
a.back-to-app:hover {{ background:#0F5230; }}
.tpl-title {{ font-size:26px !important; }}
.tpl-card {{ background:#fff; border:1px solid #BFE0CB; border-radius:12px; padding:18px;
            box-shadow:0 1px 2px rgba(15,38,27,.05); }}
.tpl-crumbs {{ font-size:12.5px; color:#6B7C70; margin-bottom:8px; }}
.tpl-crumbs a {{ color:#15803D; text-decoration:none; }}
.tpl-crumbs a:hover {{ text-decoration:underline; }}
.tpl-title {{ margin:0 0 8px; font-size:22px; font-weight:700; letter-spacing:-0.01em; }}
.tpl-meta {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap;
            font-size:12.5px; color:#6B7C70; margin-bottom:14px; }}
.tpl-badge {{ display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px;
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
.ex-tools[hidden] {{ display:none; }}
.tpl-open-orig.is-on {{ background:#16A34A; border-color:#16A34A; color:#fff; }}
/* PDF-страницы показываются картинками внутри листа визора */
.pdf-page-img {{ display:block; width:794.5px; margin:0 auto 12px; background:#fff;
                 box-shadow:0 0 0 1px #E1E7E3; }}

.tpl-row-main {{ display:grid; grid-template-columns:132px minmax(0,664px) minmax(300px,1fr);
                gap:12px; margin-bottom:14px; align-items:stretch; width:100%; max-width:100%;
                box-sizing:border-box; }}
/* Панель окна просмотра задаёт высоту ряда (один лист A4 + серые поля), поэтому она
   не растягивается: миниатюры и переменные тянутся по её низу. */
.tpl-row-main > .tpl-panel:not(.is-vars) {{ align-self:start; min-width:0; }}
/* Миниатюры — первая колонка, окно просмотра — вторая, переменные — третья. */
.tpl-rail {{ background:#fff; border:1px solid #DCEEE2; border-radius:10px; overflow:hidden;
             display:flex; flex-direction:column;
             align-self:stretch; min-width:0; position:relative; }}
.tpl-rail-head {{ padding:9px 12px; background:#F4FAF6; border-bottom:1px solid #DCEEE2;
                  font-size:13px; font-weight:700; flex:0 0 auto; }}
/* Тело колонки начинается ПОД вкладками (шапка 42px + вкладки 35px = 77px),
   иначе миниатюры накрывали вкладки. Позиционирование абсолютное — чтобы высота
   колонки по-прежнему задавалась окном просмотра, а не длиной списка миниатюр. */
.tpl-rail-body {{ padding:6px; display:block; position:absolute; inset:77px 0 0 0;
                  overflow-y:auto; overflow-x:hidden; }}
.tpl-mini {{ display:block; padding:4px; margin:0 0 6px; border:1px solid #E3EDE6; border-radius:7px;
             background:#fff; text-decoration:none; color:inherit; }}
.tpl-mini:hover {{ border-color:#17B3A3; }}
.tpl-mini.is-on {{ border-color:#0F6E63; background:#F4FAF6; box-shadow:0 0 0 2px rgba(23,179,163,.22); }}
.tpl-mini-wrap {{ position:relative; }}
/* Исключённый документ: виден на полке, но затемнён и перечёркнут крестом */
.tpl-mini {{ position:relative; }}
.tpl-mini.is-off img {{ filter:grayscale(1); opacity:.5; }}
.tpl-mini.is-off .tpl-mini-name {{ color:#8C9A91; }}
.tpl-mini-x {{ position:absolute; inset:0; display:grid; place-items:center; font-size:34px;
  font-weight:700; color:#B42318; pointer-events:none; text-shadow:0 2px 8px rgba(255,255,255,.9); }}
/* Подтверждённый документ: та же метка в центре, но зелёная — проверен и зафиксирован */
.tpl-mini-ok {{ position:absolute; inset:0; display:grid; place-items:center; font-size:34px;
  font-weight:700; color:#15803D; pointer-events:none; text-shadow:0 2px 8px rgba(255,255,255,.9); }}
.tpl-mini-why {{ display:block; font-size:10px; line-height:1.2; color:#B42318; margin-top:2px; }}
/* Квадратики согласования на миниатюре: ✓ проверено / ✕ не нужно */
.tpl-marks {{ position:absolute; top:22px; right:5px; display:flex; gap:3px; }}
.tpl-mark {{ width:20px; height:20px; padding:0; border:1px solid #CBD8D2; border-radius:6px; background:rgba(255,255,255,.94);
  color:#4B6157; font:800 11.5px/1 -apple-system,system-ui,sans-serif; cursor:pointer; }}
.tpl-mark:hover {{ border-color:#17B3A3; color:#0F6E63; }}
.tpl-mark[data-verdict="verify"].is-on {{ background:#14663A; border-color:#14663A; color:#fff; }}
.tpl-mark[data-verdict="reject"].is-on {{ background:#B42318; border-color:#B42318; color:#fff; }}
.tpl-mini-num {{ display:block; font-size:10.5px; color:#6B7C70; margin-bottom:3px; }}
.tpl-mini img {{ display:block; width:100%; height:auto; max-height:132px; object-fit:cover;
                 object-position:top; background:#fff;
                 border:1px solid #E1E7E3; border-radius:4px; }}
.tpl-mini-name {{ display:block; font-size:10.5px; line-height:1.2; margin-top:4px;
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
  transform-origin:50% 0; will-change:transform, opacity; }}
.tpl-panel.is-vars.is-swapping .tpl-panel-body {{ opacity:.12; filter:blur(.7px);
  transform: translateY(-13%) rotateX(-26deg) scaleY(.04) scaleX(.985); }}
/* тень «валика», на который накручивается список */
.tpl-panel.is-vars .tpl-panel-body::after {{ content:''; position:absolute; left:8px; right:8px; top:0; height:14px;
  border-radius:0 0 8px 8px; pointer-events:none; opacity:0; transition:opacity .35s ease;
  background:linear-gradient(180deg, rgba(15,110,99,.28), rgba(15,110,99,0)); }}
.tpl-panel.is-vars.is-swapping .tpl-panel-body::after {{ opacity:1; }}
/* ── Микроанимации смены документа: лист сворачивается в точку и разворачивается,
      пока идёт подгрузка — в центре окна крутится колёсико. ───────────────────── */
.pl-html {{ position:relative; }}
.pl-html .zp-shell {{ transition: transform .66s cubic-bezier(.45,0,.25,1), opacity .58s ease;
                      transform-origin:50% 42%; }}
.pl-html.is-collapsing .zp-shell {{ transform:scale(.02); opacity:0; }}
.doc-spinner {{ position:absolute; inset:0; display:none; align-items:center; justify-content:center; pointer-events:none;
                background:rgba(231,235,238,.75); z-index:5; }}
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
            display:inline-flex; align-items:center; justify-content:center;
            border-radius:9px 9px 0 0; cursor:pointer;
            max-width:280px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.doc-tab:hover {{ background:#fff; }}
/* Полоса вкладок визора: пять блоков одной ширины, делят строку поровну и не уползают за край.
   Оригинал · Сравнение · HTML · Масштаб − 100% + · Просмотр PDF (Андрей, 06.10.2026) */
.doc-tabs {{ display:flex; flex-wrap:nowrap; gap:6px; align-items:flex-end; overflow:hidden; }}
.doc-tabs > .doc-tab, .doc-tabs > .zp-bar, .doc-tabs > #tpl-pdf-open {{
  flex:1 1 0; min-width:0; width:auto; max-width:132px; margin:0; padding:0 6px;
  justify-content:center; text-align:center; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; box-sizing:border-box; }}
.doc-tabs > .zp-bar {{ padding:2px 5px; gap:2px; }}
#doc-tabs .zp-bar button {{ flex:1 1 0; min-width:0; padding:3px 4px; }}
#doc-tabs .zp-bar .zp-val {{ min-width:0; flex:0 0 auto; }}
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
.doc-tabs #tpl-pdf-open {{ flex:1 1 0; min-width:0; max-width:132px; align-self:center; margin:0;
  position:relative; top:-2.5px; }}
/* Серая полоса у панели переменных — та же высота и отступы, что у полос вкладок */
.vars-strip {{ height:34px; display:flex; align-items:center; padding:0 12px; overflow:hidden;
  background:#E7EBEE; border-bottom:1px solid #D5DDE3; border-radius:0; }}
.vars-strip-doc {{ font-size:11.5px; font-weight:600; color:#4B6157; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }}
.vars-strip .doc-tab {{ cursor:default; }}
/* Панель масштаба стоит в полосе вкладок вместе с кнопками — той же ширины, что и они */
#doc-tabs .zp-bar {{ margin:0; align-self:center; position:relative; top:-2.5px;
                    padding:2px 5px; border-radius:8px; gap:2px;
                    flex:1 1 0; min-width:0; max-width:132px; box-sizing:border-box; }}
#doc-tabs .zp-bar button {{ padding:3px 4px; font-size:12px; border-radius:6px; }}
#doc-tabs .zp-bar .zp-val {{ min-width:0; font-size:11.5px; flex:0 0 auto; }}
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
.tpl-panel.is-vars .tpl-panel-head {{ position:relative; z-index:2; }}
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
  display: inline-block; min-width: 22px;
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
  display:inline-flex; align-items:center; justify-content:center; user-select:none;
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
  display:inline-flex; align-items:center; justify-content:center;
}}
.var-dice:hover {{ background:#E0E7FF; border-color:#A5B4FC; }}
.var-today {{
  flex:0 0 auto; width:28px; height:28px; padding:0; cursor:pointer;
  border:1px solid #BBF7D0; background:#ECFDF5; color:#047857;
  border-radius:8px; font-size:15px; line-height:1;
  display:inline-flex; align-items:center; justify-content:center;
}}
.var-today:hover {{ background:#D1FAE5; border-color:#6EE7B7; }}
.var-side {{ display:flex; flex-direction:column; align-items:center; gap:5px; flex:0 0 auto; }}
.var-line .var-ref {{ font-size:10px; }}
.var-tools {{ display:flex; flex-direction:column; align-items:center; gap:5px; }}
.var-tools:empty {{ display:none; }}
@media (max-width: 820px) {{
  .doc-toolbar .tb-row {{ justify-content:flex-start; }}
  .doc-toolbar .tb-row .tb-btn, .doc-toolbar .tb-row .ls-btn {{ flex:0 0 auto; }}
  .doc-toolbar .tb-row .tpl-open-orig {{ margin-left:0; }}
  .doc-toolbar .tb-row .tb-btns {{ margin-left:0; width:100%; justify-content:flex-start; }}
  .doc-toolbar .tb-label {{ display:block; width:100%; }}
  .doc-toolbar .tb-label {{ min-width:0; }}
  .lang-switch {{ margin-left:0; }}
  .tpl-panel-head {{ flex-wrap:wrap; gap:6px; }}
  .doc-tabs #tpl-pdf-open {{ width:100%; justify-content:center; margin:6px 0 0; }}
  .var-side {{ gap:6px; }}
}}

/* Мобильные: номер+название переносим на свою строку, поле — во всю ширину,
   номера сдвигаем к левому краю (больше места длинным именам) */
@media (max-width: 820px) {{
  .kv-table, .kv-table tbody, .kv-table tr, .kv-table td {{ display:block; width:100%; }}
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
              display:block;
            }}
            .html-stage-wrap[data-pannable="1"] {{ cursor: grab; }}
            .html-stage-wrap.is-dragging {{ cursor: grabbing; user-select:none; }}
            .html-pan {{
              position:absolute; top:0; left:0;
              transform-origin: top left;
              will-change: transform;
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
/* Подсветка значений в визоре: цвет и фон — как были (бурый текст на светлом фоне),
   убрано ТОЛЬКО подчёркивание (Андрей, 16.10.2026). Служебные data-var/data-src
   остаются: подсказка и переход к переменной работают. */
.html-stage .var-hl, .doc-html-stage .var-hl {{
  background:#FEF3C7 !important; color:#78350F !important; padding:1px 5px !important;
  border:0 !important; border-bottom:0 !important; box-shadow:none !important;
  border-radius:3px !important; text-decoration:none !important;
}}
.html-stage .var-hl *{{ text-decoration:none !important; border-bottom:0 !important; }}
.var-hl-inline {{ background:transparent; padding:0; border:0; color:#78350F;
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
.tpl-gen-btn small {{ display:block; font-weight:400; font-size:11px;
                      opacity:0.9; margin-top:3px; }}

.tpl-preview {{ background:#1F2937; border:1px solid #DCEEE2; border-radius:10px;
                padding:0; display:block; overflow:auto; min-height:76vh; }}
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
.prod-sum::-webkit-details-marker {{ display:none; }}
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
.pi-block {{ padding:8px 0; border-bottom:1px solid #EDF3EF; font-size:13px; line-height:1.5; color:#243029; }}
.pi-block:last-child {{ border-bottom:0; }}
.pi-block b {{ display:block; font-size:11.5px; text-transform:uppercase; letter-spacing:.04em;
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
    if _prod:
        # Конструктор продукта: общие переменные группы — над рабочей областью документа
        body += _group_vars_panel(int(_prod["id"]), int(template_id))
    try:  # группа документа — для пути в шапке («Конструктор PDF › Банковские справки › …»)
        _groups = _group_by_type([t])
        _grp = _groups[0][0] if _groups and isinstance(_groups[0], (list, tuple)) else ""
    except Exception:
        _grp = ""
    if _prod:
        _prod_short = SHORT_NAME.get(_prod.get("code"), _prod.get("name") or "")
        _crumbs = (f'<a href="/">Главная</a> &rsaquo; <a href="/templates">Конструктор PDF</a>'
                   f' &rsaquo; <a href="/templates" title="Все продукты">{_prod_short}</a>'
                   f' &rsaquo; <b>{t["title"]}</b>')
        _page_title = f'Конструктор · {_prod_short}'
    else:
        _crumbs = (f'<a href="/">Главная</a> &rsaquo; <a href="/templates">Конструктор PDF</a>'
                   + (f' &rsaquo; <a href="/templates" title="Все документы этого типа">{_grp}</a>'
                      if _grp else '')
                   + f' &rsaquo; <b>{t["title"]}</b>')
        _page_title = t["title"]
    if _embed:
        # Встроенный вид для страницы заявки: только рабочая область, без шапки и крошек
        return ('<div class="tpl-embed">' + body + _LANG_CSS + _LANG_JS + _SYNC_JS + CTOR_HL
                + '<style>.tpl-embed .tpl-title,.tpl-embed .tpl-crumbs{display:none !important}'
                  '.tpl-embed{display:block}</style></div>')
    return render(_page_title, "templates", body + _LANG_CSS + _LANG_JS + _SYNC_JS + CTOR_HL,
                  crumbs=_crumbs)

LIVE_UPDATE_JS = """<script>
// === Вкладки колонки миниатюр: «Наши» шаблоны / «Оригиналы» клиента ===
(function(){
  var box=document.getElementById('rail-tabs'); if(!box) return;
  var ours=document.getElementById('tpl-rail-body'), orig=document.getElementById('tpl-rail-orig');
  function show(which){
    if(ours) ours.hidden = (which!=='ours');
    if(orig) orig.hidden = (which==='ours');
    box.querySelectorAll('.rail-tab').forEach(function(x){
      x.classList.toggle('is-on', x.getAttribute('data-rail')===which);
    });
  }
  box.addEventListener('click', function(e){
    var b=e.target.closest && e.target.closest('.rail-tab'); if(!b) return;
    e.preventDefault(); show(b.getAttribute('data-rail'));
  });
  if(location.search.indexOf('rail=orig')>-1) show('orig');
})();

// === Live-обновление HTML при изменении input ===
(function() {
  /* Возврат в заявку: если значения менялись — спросим, сохранить ли */
  (function(){
    var back = document.getElementById('back-to-app');
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
      var values = {};
      document.querySelectorAll('.pl-vars input[name]').forEach(function(inp){ values[inp.name] = inp.value; });
      var fd = new FormData();
      fd.append('values_json', JSON.stringify(values));
      fetch('/applications/' + saveBtn.dataset.app + '/doc/' + saveBtn.dataset.tpl + '/save-values',
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
    var cardEl = document.querySelector('.tpl-card');
    var APP = cardEl ? parseInt(cardEl.getAttribute('data-app') || '0', 10) : 0;
    if (!APP) return;
    var SEL = '.pl-vars input[name], .pl-vars textarea[name], .pl-vars select[name]';
    function saveOne(name, value){
      var fd = new FormData();
      fd.append('key', name);
      fd.append('value', value == null ? '' : value);
      fd.append('source', 'card');
      return fetch('/applications/' + APP + '/review/value',
                   {method:'POST', body:fd, credentials:'same-origin',
                    headers:{'X-Requested-With':'fetch'}}).catch(function(){});
    }
    function collect(){
      var vals = {};
      document.querySelectorAll(SEL).forEach(function(el){ vals[el.name] = el.value; });
      return vals;
    }
    var tmr = null;
    function autoSave(el, delay){
      clearTimeout(tmr);
      tmr = setTimeout(function(){ saveOne(el.name, el.value); }, delay);
    }
    document.addEventListener('change', function(e){
      var el = e.target && e.target.closest ? e.target.closest(SEL) : null;
      if (el) autoSave(el, 350);
    }, true);
    document.addEventListener('input', function(e){
      var el = e.target && e.target.closest ? e.target.closest(SEL) : null;
      if (el) autoSave(el, 900);
    }, true);
    /* Применить организацию: одна компания = вся группа её переменных.
       В договоре об организации говорится в пяти местах (название в шапке, юр.
       название в тексте, название в кавычках, юр. адрес, ИНН/КПП/ОГРН в абзаце и
       в подвале) — меняешь компанию, подставляются все зависимые значения. */
    function applyEmployer(name){
      if (!name) return;
      var fd = new FormData();
      fd.append('title', name);
      return fetch('/applications/' + APP + '/review/employer_apply',
                   {method:'POST', body:fd, credentials:'same-origin',
                    headers:{'X-Requested-With':'fetch'}})
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(d){
          if (!d || !d.values) return;
          /* Значения полей меняем и сразу шлём событие input: на него завязаны
             и подсветка в HTML-визоре (sync), и автосохранение в заявку. Без этого
             документ визуально не менялся до перезагрузки страницы. */
          Object.keys(d.values).forEach(function(k){
            var f = document.querySelector('.pl-vars input[name="' + k + '"], .pl-vars textarea[name="' + k + '"]');
            if (!f) return;
            f.value = d.values[k] || '';
            f.dispatchEvent(new Event('input', {bubbles: true}));
          });
          if (window.zpScan) setTimeout(function(){ window.zpScan(); }, 60);
        })
        .catch(function(){});
    }
    /* Выпадающий список рядом с переменной №1 — организация из пула. */
    document.addEventListener('change', function(e){
      var sel = e.target;
      if (!sel || !sel.classList || !sel.classList.contains('emp-pick')) return;
      var fld = document.querySelector('.pl-vars input[name="company_name_in_quotes"]');
      if (!fld) return;
      if (sel.value === '__own__') {
        fld.value = '';
        fld.focus();          // дальше администратор пишет название сам
        return;
      }
      if (!sel.value) return;
      fld.value = sel.value;
      applyEmployer(sel.value);
    }, true);
    /* Переменные организации созависимы: администратор правит любую из связанных
       величин (название, юридическое название, адрес, ИНН, КПП, ОГРН) — система
       находит организацию в пуле и подставляет всю группу целиком. Если значение
       не из архива — остаётся ручной ввод, остальные поля не трогаем. */
    var EMP_VARS = ['company_name_in_quotes', 'employer_name', 'company_registered_address',
                    'company_inn', 'company_kpp', 'company_ogrn'];
    document.addEventListener('change', function(e){
      var el = e.target;
      if (!el || !el.name || EMP_VARS.indexOf(el.name) < 0) return;
      var v = (el.value || '').trim();
      if (!v) return;
      applyEmployer(v);
    }, true);
    /* Метка на миниатюре — отражение нажатой кнопки: ✕ или ✓ по центру листа.
       Рисуем сразу по ответу сервера, чтобы не ждать перезагрузки страницы. */
    function paintMini(tpl, st){
      var off = st === 'rejected', ok = (st === 'verified' || st === 'sent');
      document.querySelectorAll('.tpl-mini[data-tpl="' + tpl + '"]').forEach(function(tile){
        tile.classList.toggle('is-off', off);
        tile.classList.toggle('is-ok', ok);
        var host = tile.querySelector('.tpl-mini-name') || null;
        var x = tile.querySelector('.tpl-mini-x');
        var m = tile.querySelector('.tpl-mini-ok');
        if (off && !x){ x = document.createElement('span'); x.className = 'tpl-mini-x'; x.textContent = '✕'; tile.insertBefore(x, host); }
        if (!off && x) x.remove();
        if (ok && !m){ m = document.createElement('span'); m.className = 'tpl-mini-ok'; m.textContent = '✓'; tile.insertBefore(m, host); }
        if (!ok && m) m.remove();
      });
      railReorder();
    }
    /* Порядок в столбике документов: нужные — по номеру документа (вниз по возрастанию),
       отмеченные крестиком уезжают в конец и возвращаются на своё место, когда крестик снят. */
    function railReorder(){
      var body = document.getElementById('tpl-rail-body');
      if (!body) return;
      var tiles = Array.prototype.slice.call(body.querySelectorAll('.tpl-mini-wrap'));
      if (tiles.length < 2) return;
      var key = function(t){
        var inner = t.querySelector('.tpl-mini') || t;
        var off = inner.classList.contains('is-off') ? 1 : 0;
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
    document.addEventListener('click', function(e){
      var b = e.target && e.target.closest ? e.target.closest('.rv-mark') : null;
      if (!b) return;
      if (b.getAttribute('data-saved') === '1'){ b.removeAttribute('data-saved'); return; }
      e.preventDefault(); e.stopImmediatePropagation();
      var tpl = b.getAttribute('data-tpl') || '';
      var isVerify = (b.getAttribute('data-verdict') === 'verify');
      var SEL = '.rv-mark[data-tpl="' + tpl + '"], .doc-verdict-float button[data-tpl="' + tpl + '"], .tpl-mark[data-tpl="' + tpl + '"], .pdf-vbtn[data-tpl="' + tpl + '"]';
      var marks = document.querySelectorAll(SEL);
      /* Повторный клик по той же кнопке снимает выбор — рисуем это сразу,
         сервер подтверждает (verify/reject у него переключатели). */
      var wasOn = b.classList.contains('is-on');
      marks.forEach(function(x){ x.classList.remove('is-on', 'rv-on-ok', 'rv-on-no'); });
      if(!wasOn){
        marks.forEach(function(x){
          var ok = (x.getAttribute('data-verdict') === 'verify');
          if(ok === isVerify){
            x.classList.add('is-on');
            if(x.classList.contains('rv-mark')) x.classList.add(ok ? 'rv-on-ok' : 'rv-on-no');
          }
        });
      }
      /* Сразу показываем результат нажатия: метка по центру миниатюры и порядок
         в столбике меняются моментально, сервер подтверждает состояние в базе.
         Значения документа уходят фоном и вердикт больше не задерживают. */
      var kind = isVerify ? 'verify' : 'reject';
      var app = (document.body.getAttribute('data-app')
                 || (typeof APP !== 'undefined' && APP)
                 || (typeof APP_ID !== 'undefined' && APP_ID) || 0);
      var wasState = wasOn ? (isVerify ? 'verified' : 'rejected') : '';
      paintMini(tpl, wasOn ? '' : (isVerify ? 'verified' : 'rejected'));
      /* Значения полей сохраняются по мере правки (autoSave). Пачку сохранений
         здесь не отправляем: она обгоняла вердикт и сбрасывала только что
         поставленную галочку. */
      fetch('/applications/' + app + '/doc/' + tpl + '/' + kind,
             {method:'POST', credentials:'same-origin', keepalive:true,
                    headers:{'X-Requested-With':'fetch'}})
        .then(function(r){ return r.json(); })
        .then(function(d){
          if (d && d.ok === false && d.error && d.can_force && kind === 'verify'){
            /* Не заполнены поля: фиксируем документ как есть — галочка должна
               вставать с первого нажатия, без лишнего диалога. */
            fetch('/applications/' + app + '/doc/' + tpl + '/verify?force=1',
                   {method:'POST', credentials:'same-origin', keepalive:true,
                    headers:{'X-Requested-With':'fetch'}})
              .then(function(r){ return r.json(); })
              .then(function(){
                paintMini(tpl, 'verified');
                document.querySelectorAll('.rv-mark[data-tpl="' + tpl + '"], .tpl-mark[data-tpl="' + tpl + '"], .pdf-vbtn[data-tpl="' + tpl + '"]')
                  .forEach(function(x){ if (x.getAttribute('data-verdict') === 'verify') x.classList.add('is-on'); });
                if (window.__rvRefresh) window.__rvRefresh();
              })
              .catch(function(){ paintMini(tpl, wasState); });
            return;
          }
          if (d && d.ok === false && d.error){
            /* сервер отказал окончательно — возвращаем как было */
            var lbl = document.getElementById('rv-thumb-status-' + tpl);
            if (lbl){ lbl.textContent = d.error; lbl.classList.add('rv-warn');
              setTimeout(function(){ lbl.classList.remove('rv-warn'); }, 6000); }
            paintMini(tpl, wasState);
            document.querySelectorAll('[data-tpl="' + tpl + '"]').forEach(function(x){
              x.classList.remove('is-on', 'rv-on-ok', 'rv-on-no'); });
            return;
          }
          var st = '';
          if (d && d.verified === true) st = 'verified';
          else if (d && d.rejected === true) st = 'rejected';
          paintMini(tpl, st);
          document.querySelectorAll('.rv-mark[data-tpl="' + tpl + '"], .doc-verdict-float button[data-tpl="' + tpl + '"], .tpl-mark[data-tpl="' + tpl + '"], .pdf-vbtn[data-tpl="' + tpl + '"]')
            .forEach(function(x){
              var ok = (x.getAttribute('data-verdict') === 'verify');
              var on = (ok && st === 'verified') || (!ok && st === 'rejected');
              x.classList.toggle('is-on', on);
              if (x.classList.contains('rv-mark')) x.classList.toggle(ok ? 'rv-on-ok' : 'rv-on-no', on);
            });
          if (window.__rvRefresh) window.__rvRefresh();
        })
        .catch(function(){ paintMini(tpl, wasState); });
    }, true);
    /* Рамка с ✓ / ✕ стоит поверх листа: держим её у левого верхнего угла листа,
       чтобы при смене масштаба и прокрутке она всегда была на документе. */
    (function(){
      var f = document.querySelector('.doc-verdict-float');
      var pl = f ? f.closest('.pl-html') : null;
      if (!f || !pl) return;
      function place(){
        var sheet = pl.querySelector('.sheet') || pl.querySelector('#html-stage');
        if (!sheet) return;
        var pr = pl.getBoundingClientRect(), sr = sheet.getBoundingClientRect();
        var lx = Math.round(sr.left - pr.left) + 10, ty = Math.round(sr.top - pr.top) + 10;
        f.style.left = Math.max(6, Math.min(lx, Math.max(6, pr.width - 90))) + 'px';
        f.style.top  = Math.max(6, ty) + 'px';
      }
      place();
      window.addEventListener('resize', place);
      document.addEventListener('scroll', place, true);
      document.addEventListener('wheel', function(){ setTimeout(place, 60); }, {passive:true, capture:true});
      var host = pl.querySelector('.zp-host');
      if (host) host.addEventListener('scroll', place);
      /* Без таймера: рамка переставляется по событиям (масштаб, прокрутка, окно),
         иначе лист дёргается при каждом пересчёте. */
    })();
  })();

  const varsForm = document.getElementById('vars-form');
  const stage = document.getElementById('html-stage');
  if (!varsForm || !stage) return;

  // Запомним оригинальные HTML-плейсхолдеры один раз (после рендера страницы)
  // Чтобы подставлять значения без запроса на сервер
  const placeholders = []; // список элементов .var-hl в порядке появления
  for (const el of stage.querySelectorAll('.var-hl')) {
    const m = (el.textContent.match(/[{][{]\s*([a-zA-Z0-9_]+)\s*[}][}]/) || []);
    if (m[1]) placeholders.push({ el: el, name: m[1] });
  }

  function refresh() {
    const inputs = varsForm.querySelectorAll('input[data-var]');
    const values = {};
    for (const inp of inputs) {
      const v = (inp.value || '').trim();
      if (v) values[inp.dataset.var] = v;
    }
    let cnt = 0;
    for (const ph of placeholders) {
      if (values[ph.name] !== undefined) {
        const safe = values[ph.name]
          .replace(/&/g, '&')
          .replace(/</g, '<')
          .replace(/>/g, '>')
          .replace(/"/g, '"');
        ph.el.innerHTML = '<span style="background:#DCFCE7;color:#15803D;padding:1px 5px;border-radius:3px;font-weight:700">' +
                          safe + '</span>';
        cnt++;
      } else {
        ph.el.innerHTML = '{{ ' + ph.name + ' }}';
      }
    }
    const badge = document.getElementById('live-counter');
    if (badge) badge.textContent = cnt > 0 ? 'подставлено: ' + cnt + ' / ' + placeholders.length : 'нет подстановок';
  }

  function escapeHtml(s) {
    return s.replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>').replace(/"/g, '"');
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


@bp.route("/templates/<int:template_id>/convert", methods=["POST"])
@login_required
def convert(template_id: int):
    t = _template(template_id)
    try:
        result = pdf2html.run_conversion({"id": t["code"], "source_pdf": t["source_pdf"],
                                      "qa_ignore": []})
    except Exception as exc:                            # noqa: BLE001
        flash(f"Конвертация не удалась: {exc}", "error")
        return redirect(url_for("templates.card", template_id=template_id))

    db.exec_sql("UPDATE templates SET html_path=?, pages=?, status=?, qa_json=?, updated_at=datetime('now') "
                "WHERE id=?",
                (str(HTML_DIR / t["code"] / "template.html"), result.get("pages") or 0,
                 result["status"], json.dumps(result["qa"], ensure_ascii=False), template_id))
    db.exec_sql("DELETE FROM template_variables WHERE template_id=?", (template_id,))
    for i, var in enumerate(result["variables"]):
        db.exec_sql("""INSERT INTO template_variables
                       (template_id, name, label, vtype, format, source_kind, source_ref,
                        default_value, sort_order)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (template_id, var["name"], var.get("label") or var["name"],
                     var.get("type") or "text", var.get("format") or "",
                     var.get("source_kind") or "client", var.get("source_ref") or "",
                     var.get("default") or "", i))
    qa = result["qa"]
    db.log_event("template", template_id, "converted",
                 payload=f'переменных: {len(result["variables"])}')
    flash(f'Готово: переменных {len(result["variables"])}, '
          f'потерянных слов {len(qa.get("missing_words") or [])}')
    return redirect(url_for("templates.card", template_id=template_id))


@bp.route("/templates/<int:template_id>/save-defaults", methods=["POST"])
@login_required
def save_defaults(template_id: int):
    """Сохраняет значения переменных как default_value + запоминает в памяти.

    Если форма пришла из конструктора продукта (скрытое поле product_id), значения тех
    переменных, которые есть в других документах группы, раскладываются и по ним: заказчик
    правит документ группы, и та же фамилия, дата рождения или адрес меняются во всей группе.
    """
    t = _template(template_id)
    variables = vars_repo.names(template_id)
    changed = 0
    for v in variables:
        vname = v["name"]
        val = (request.form.get(vname) or "").strip()
        if val:
            db.exec_sql("UPDATE template_variables SET default_value=? WHERE template_id=? AND name=?",
                        (val, template_id, vname))
            # запомнить в памяти (если не уникальное)
            if vname not in {"name","surname","patronymic","full_name","full_name_latin",
                              "birth_date","date_of_birth","passport_series","passport_number",
                              "address_reg","address_live","card_mask","ref_no","phone","email",
                              "inn","client_name","bank_phone","bank_manager_name","doc_no"}:
                try:
                    db.remember_value(vname, val)
                except Exception:
                    pass
            changed += 1
    # Автозапоминание описаний: администратор выбрал профессию, подобрал/написал
    # текст и подтвердил его — формулировка уходит в память парой RU/EN, чтобы
    # дальше предлагаться из «кусочков» без обращения к модели.
    try:
        from services import cv_gen as _cv
        from services import translate as _T
        _prof = (request.form.get("cv_profession") or "").strip()
        _code = _cv.code_by_title(_prof) if _prof else ""
        _cvnames = [v["name"] for v in variables
                    if v["name"].startswith("cv_") and any(
                        k in v["name"] for k in ("summary", "profile", "about",
                                                 "duties", "responsib", "skills", "descript"))]
        remembered = 0
        for _vn in _cvnames:
            if remembered >= 3:
                break
            _val = (request.form.get(_vn) or "").strip()
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
            if _cv.remember_phrase(_code or "_common", _val, _ru):
                remembered += 1
    except Exception:
        pass
    try:
        _actor = (current_user() or {}).get("login") or "system"
    except Exception:
        _actor = "system"
    db.log_event("template", template_id, "defaults_saved", actor=_actor)
    # Конструктор продукта: значения разошлись по всей группе документов
    _pid = request.form.get("product_id", type=int)
    _group_changed = 0
    if _pid:
        _others = db.q("SELECT t.id FROM templates t JOIN product_documents pd "
                       "ON pd.template_id=t.id WHERE pd.product_id=? AND t.id<>? "
                       "AND COALESCE(t.status,'ok') NOT IN ('merged','hidden')",
                       (_pid, template_id)) or []
        for v in variables:
            _val = (request.form.get(v["name"]) or "").strip()
            if not _val:
                continue
            for _o in _others:
                try:
                    if db.q1("SELECT 1 FROM template_variables WHERE template_id=? AND name=?",
                             (_o["id"], v["name"])):
                        db.exec_sql("UPDATE template_variables SET default_value=? "
                                    "WHERE template_id=? AND name=?",
                                    (_val, _o["id"], v["name"]))
                        _group_changed += 1
                except Exception:  # noqa: BLE001
                    continue
    if _pid:
        flash(f"Значения сохранены ({changed} шт.) и разложены по группе продукта "
              f"({_group_changed} записей)")
        return redirect(url_for("templates.product_constructor", product_id=_pid,
                                tpl=template_id))
    flash(f"Значения сохранены ({changed} шт.)")
    return redirect(url_for("templates.card", template_id=template_id))


@bp.route("/templates/product/<int:product_id>/constructor")
@login_required
def product_constructor(product_id: int):
    """Конструктор продукта: работаем не с отдельным документом, а с группой продукта.

    Заказчик открывает продукт (например «Мостовая виза») и попадает в конструктор, где
    в колонке миниатюр — только документы этой группы, а общие переменные задаются один раз
    на всю группу (`_group_vars_panel`).
    """
    docs = db.q("SELECT t.id, t.title FROM templates t "
                "JOIN product_documents pd ON pd.template_id=t.id "
                "WHERE pd.product_id=? AND COALESCE(t.status,'ok') NOT IN ('merged','hidden') "
                "ORDER BY pd.sort_order, COALESCE(t.doc_index, 999), t.title", (product_id,)) or []
    if not docs:
        flash("В этом продукте пока нет документов", "error")
        return redirect(url_for("templates.page"))
    tpl_id = request.args.get("tpl", type=int)
    if not tpl_id or tpl_id not in {int(d["id"]) for d in docs}:
        tpl_id = int(docs[0]["id"])
    # Реальные данные клиента: берём заявку тестового прогона продукта (метка real_test),
    # иначе — последнюю заявку этого продукта. Тогда миниатюры наших документов и визор
    # показывают те же данные, что и клиентские файлы в соседней вкладке.
    _app = request.args.get("app", type=int)
    if not _app:
        _r = db.q1("""SELECT a.id FROM applications a JOIN clients c ON c.id=a.client_id
                      WHERE a.product_id=?
                      ORDER BY (a.record_kind='real_test') DESC, a.id DESC LIMIT 1""",
                   (product_id,))
        _app = int(_r["id"]) if _r else None
    return card(tpl_id, _app_id=_app, _product_id=product_id)


@bp.route("/templates/product/<int:product_id>/save-shared", methods=["POST"])
@login_required
def save_shared_vars(product_id: int):
    """Значения общих переменных продукта раскладываем по всем документам группы."""
    docs = db.q("SELECT t.id FROM templates t JOIN product_documents pd ON pd.template_id=t.id "
                "WHERE pd.product_id=? AND COALESCE(t.status,'ok') NOT IN ('merged','hidden')",
                (product_id,)) or []
    ids = [int(d["id"]) for d in docs]
    changed = 0
    for key, val in request.form.items():
        if not re.fullmatch(r"[A-Za-z0-9_]+", key or ""):
            continue
        val = (val or "").strip()
        if not val or not ids:
            continue
        for tid_ in ids:
            try:
                if db.q1("SELECT 1 FROM template_variables WHERE template_id=? AND name=?",
                         (tid_, key)):
                    db.exec_sql("UPDATE template_variables SET default_value=? "
                                "WHERE template_id=? AND name=?", (val, tid_, key))
                    changed += 1
            except Exception:  # noqa: BLE001
                continue
        try:
            db.remember_value(key, val)
        except Exception:  # noqa: BLE001
            pass
    try:
        _actor = (current_user() or {}).get("login") or "system"
    except Exception:  # noqa: BLE001
        _actor = "system"
    db.log_event("product", product_id, "shared_vars_saved", payload=str(changed), actor=_actor)
    flash(f"Общие значения разложены по документам группы ({changed} записей)")
    return redirect(url_for("templates.product_constructor", product_id=product_id))


@bp.route("/templates/<int:template_id>/add-variable", methods=["POST"])
@login_required
def add_variable(template_id: int):
    """Добавляет новую переменную в template_variables."""
    from flask import jsonify, request as _req
    t = _template(template_id)
    if not t:
        return jsonify({"ok": False, "error": "шаблон не найден"}), 404
    payload = _req.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip().lower()
    default = (payload.get("default_value") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "пустое имя"}), 400
    # валидация имени
    import re as _re
    if not _re.match(r"^[a-z][a-z0-9_]{1,40}$", name):
        return jsonify({"ok": False, "error": "имя: латиница, цифры, _; начинается с буквы"}), 400
    # проверим что такой переменной ещё нет
    exists = db.q1("SELECT id FROM template_variables WHERE template_id=? AND name=?",
                   (template_id, name))
    if exists:
        # обновим default_value если передано
        if default:
            db.exec_sql("UPDATE template_variables SET default_value=? WHERE id=?",
                        (default, exists["id"]))
        return jsonify({"ok": True, "id": exists["id"], "updated": True})
    # добавим
    sort_order = (db.q1("SELECT COALESCE(MAX(sort_order),0)+10 AS so FROM template_variables WHERE template_id=?",
                        (template_id,)) or {}).get("so", 100)
    cur = db.exec_sql(
        "INSERT INTO template_variables (template_id, name, label, default_value, sort_order) VALUES (?,?,?,?,?)",
        (template_id, name, name, default, sort_order)
    )
    db.log_event("template", template_id, "variable_added",
                 actor=current_user()["login"], payload={"name": name})
    return jsonify({"ok": True, "id": getattr(cur, 'lastrowid', None), "updated": False})


@bp.route("/templates/<int:template_id>/render", methods=["POST"])
@login_required
def make_pdf(template_id: int):
    # Если нажата отдельная кнопка — сохраняем только правила и уходим на карточку
    if request.form.get("action") == "save_rules":
        _n = 0
        for v in vars_repo.names(template_id):
            rule = request.form.get(f"rule_{v['name']}")
            if rule is not None:
                db.exec_sql(
                    "UPDATE template_variables SET rule_note=? WHERE template_id=? AND name=?",
                    (rule.strip(), template_id, v["name"]))
                _n += 1
        flash(f"Сохранено правил: {_n}")
        return redirect(url_for("templates.card", template_id=template_id) + "#rules")

    t = _template(template_id)
    html_file = HTML_DIR / t["code"] / "template.html"
    if not html_file.exists():
        flash("Сначала сконвертируйте шаблон в HTML", "error")
        return redirect(url_for("templates.card", template_id=template_id))
    html = html_file.read_text(encoding="utf-8")
    values = {v["name"]: (request.form.get(v["name"]) or "").strip()
              for v in vars_repo.names(template_id)}
    for name, value in values.items():
        db.exec_sql("UPDATE template_variables SET default_value=? WHERE template_id=? AND name=?",
                    (value, template_id, name))
    # сохранить правила формирования (если присланы)
    _saved_rules = 0
    for v in vars_repo.names(template_id):
        rule = request.form.get(f"rule_{v['name']}")
        if rule is not None:
            rule = rule.strip()
            db.exec_sql(
                "UPDATE template_variables SET rule_note=? WHERE template_id=? AND name=?",
                (rule, template_id, v["name"]))
            _saved_rules += 1
    if _saved_rules:
        flash(f"Сохранено правил: {_saved_rules}")
    # ЕДИНЫЙ рендер: тот же код, что в карточке заявки, боте и автоподготовке
    filled = doc_render.fill(html, values, keep_unfilled=True, template_code=t["code"])
    tmp_html = HTML_DIR / t["code"] / "filled.html"
    tmp_html.write_text(filled, encoding="utf-8")
    out_pdf = RENDER_DIR / doc_render.doc_filename(t["title"] or t["code"], values, code=t["code"])
    try:
        pdf2html.render_pdf(tmp_html, out_pdf)
    except Exception as exc:                            # noqa: BLE001
        flash(f"PDF не собрался: {exc}", "error")
        return redirect(url_for("templates.card", template_id=template_id))
    db.log_event("template", template_id, "rendered", payload=out_pdf.name)
    flash(f"PDF сформирован: {out_pdf.name}")
    return redirect(url_for("templates.card", template_id=template_id) + f"?pdf={out_pdf.name}#preview")


@bp.route("/templates/<int:template_id>/cv/professions")
@login_required
def tpl_cv_professions(template_id: int):
    """Список профессий для панели описания в конструкторе документа."""
    from services import cv_gen
    items = [{"code": p.get("code"), "ru": p.get("ru"), "en": p.get("en")}
             for p in (cv_gen.load_positions() or [])]
    return jsonify({"ok": True, "items": items})


@bp.route("/templates/<int:template_id>/cv/phrases")
@login_required
def tpl_cv_phrases(template_id: int):
    """Готовые предложения по профессии — для сборки описания «плюсиками».

    Отдаём парами: русский текст для чтения администратором, английский — для
    подстановки в документ.
    """
    from services import cv_gen
    code = (request.args.get("code") or "").strip()
    job = (request.args.get("job") or "").strip()
    # Должность важнее профессии: администратор мог поставить конкретную должность
    # («Sales Manager»), и кусочки должны подбираться под неё, а не под общий профиль.
    if job:
        try:
            _jc = cv_gen.detect_position(job)
            if _jc:
                code = _jc
        except Exception:
            pass
    var = (request.args.get("var") or "cv_summary").strip()
    pairs = cv_gen.position_phrases_pairs(code, var) if code else []
    return jsonify({"ok": True, "code": code, "pairs": pairs,
                    "items": [p["en"] for p in pairs]})


@bp.route("/templates/<int:template_id>/cv/random", methods=["POST"])
@login_required
def tpl_cv_random(template_id: int):
    """«Кубик»: описание профессии из нескольких предложений (по умолчанию — трёх)."""
    from services import cv_gen
    raw = request.get_json(silent=True) or {}
    code = (raw.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "выберите профессию"})
    try:
        n = int(raw.get("n") or 3)
    except Exception:
        n = 3
    text = cv_gen.summary_random(code, n=n) or ""
    if not text:
        return jsonify({"ok": False, "error": "нет готовых предложений для этой профессии"})
    return jsonify({"ok": True, "text": text, "value": text, "profession": code})


JOB_STEP_PT = 128.0


def _job_var_exists(tpl_id: int, name: str) -> bool:
    return bool(db.q1("SELECT 1 FROM template_variables WHERE template_id=? AND name=?",
                      (tpl_id, name)))


def _clone_job_block(tpl_code: str, n: int) -> bool:
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
    if ('cv_job%d_title' % n) in html:
        return True
    prev = n - 1
    lines = html.splitlines()

    def first_top(k: int):
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
            if any(('cv_job%d_%s' % (prev, x)) in ln for x in ('period', 'company', 'bullets')):
                gate = top if gate is None else min(gate, top)
    if gate is not None:
        gate -= 2.0            # строки блока опыта, но не одноимённое поле в шапке
    max_prev = max(prev_tops) if prev_tops else None

    t_prev, t_before = first_top(prev), (first_top(prev - 1) if prev > 1 else None)
    if t_prev is not None and t_before is not None and t_prev > t_before:
        step = t_prev - t_before          # свой шаг формата
    else:
        step = JOB_STEP_PT

    out, added = [], 0
    for ln in lines:
        out.append(ln)
        if ('cv_job%d_' % prev) in ln:
            m = re.search(r'top:([0-9.]+)pt', ln)
            if gate is not None and m and float(m.group(1)) < gate:
                continue          # то же имя в шапке документа — не блок опыта
            new = ln.replace('cv_job%d_' % prev, 'cv_job%d_' % n)
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
    parts = names or ('title', 'period', 'company', 'bullets')
    cnt = 0
    for part in parts:
        r = db.q1("SELECT * FROM template_variables WHERE template_id=? AND name=?",
                  (tpl_id, 'cv_job%d_%s' % (prev, part)))
        if not r:
            continue
        newname = 'cv_job%d_%s' % (n, part)
        if _job_var_exists(tpl_id, newname):
            continue
        db.exec_sql(
            "INSERT INTO template_variables(template_id,name,label,vtype,format,source_kind,"
            "source_ref,default_value,sort_order,rule_note,approved,examples_json) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (tpl_id, newname, (r.get('label') or '').replace(str(prev), str(n)),
             r.get('vtype') or 'text', r.get('format') or '', r.get('source_kind') or 'client',
             '', '', (r.get('sort_order') or 0) + 10, r.get('rule_note') or '', 0, '[]'))
        cnt += 1
    return cnt


def _clone_block(tpl_code: str, prev: str, new: str) -> bool:
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
            new_ln = ln.replace(prev, new)
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


@bp.route("/templates/<int:template_id>/cv/add_job", methods=["POST"])
@login_required
def tpl_cv_add_job(template_id: int):
    """«＋ Ещё место работы»: дублирует блок предыдущего места вторым порядком (6.1/7.1/8.1/9.1).

    Новые переменные не заводятся — тот же набор полей получает второй порядок:
    cv_job2_1_title, cv_job2_1_period, cv_job2_1_company, cv_job2_1_bullets.
    """
    t = _template(template_id)
    m = 1
    while (_job_var_exists(template_id, 'cv_job2_%d_title' % m)
           or _job_var_exists(template_id, 'cv_job2_%d_bullets' % m)):
        m += 1
    html_ok = _clone_block(t["code"], 'cv_job2_', 'cv_job2_%d_' % m)
    try:
        html = (HTML_DIR / t["code"] / 'template.html').read_text(encoding='utf-8')
    except Exception:
        html = ''
    cnt = 0
    for part in ('title', 'period', 'company', 'bullets'):
        if ('cv_job2_%s' % part) not in html:
            continue
        r = db.q1("SELECT * FROM template_variables WHERE template_id=? AND name=?",
                  (template_id, 'cv_job2_' + part))
        if not r:
            continue
        nm = 'cv_job2_%d_%s' % (m, part)
        if _job_var_exists(template_id, nm):
            continue
        db.exec_sql(
            "INSERT INTO template_variables(template_id,name,label,vtype,format,source_kind,"
            "source_ref,default_value,sort_order,rule_note,approved,examples_json) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (template_id, nm, (r.get('label') or nm).replace('(место 2)', '(место 2.%d)' % m),
             r.get('vtype') or 'text', r.get('format') or '', r.get('source_kind') or 'client',
             '', '', (r.get('sort_order') or 0) + 20 + m, r.get('rule_note') or '', 0, '[]'))
        cnt += 1
    return jsonify({"ok": True, "job": "2.%d" % m, "html": html_ok, "vars": cnt})


@bp.route("/templates/<int:template_id>/cv/roll_experience", methods=["POST"])
@login_required
def tpl_cv_roll_experience(template_id: int):
    """Подобрать весь опыт: 2–3 места с периодами, компаниями и обязанностями."""
    from services import cv_gen
    raw = request.get_json(silent=True) or {}
    code = (raw.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "выберите профессию"})
    level = (raw.get("level") or "medium").strip() or "medium"
    try:
        count = int(raw.get("count") or 3)
    except Exception:
        count = 3
    return jsonify({"ok": True, "items": cv_gen.gen_experience(code, level, count)})


@bp.route("/templates/<int:template_id>/cv/universities")
@login_required
def tpl_cv_universities(template_id: int):
    """Учебные заведения города места рождения (переменная «место рождения»)."""
    from services import cv_gen
    city = (request.args.get("city") or "").strip()
    return jsonify({"ok": True, "city": city, "label": cv_gen.city_label(city),
                    "items": cv_gen.universities_for_city(city)})


@bp.route("/templates/<int:template_id>/cv/majors")
@login_required
def tpl_cv_majors(template_id: int):
    """Специальности по профилю выбранного вуза (поле «образование»)."""
    from services import cv_gen
    uni = (request.args.get("university") or "").strip()
    return jsonify({"ok": True, "university": uni,
                    "profile": cv_gen.university_profile(uni),
                    "items": cv_gen.education_options(uni)})


@bp.route("/templates/<int:template_id>/cv/degrees")
@login_required
def tpl_cv_degrees(template_id: int):
    """Пул формулировок образования для выпадающего списка."""
    from services import cv_gen
    return jsonify({"ok": True, "items": cv_gen.degree_options()})


@bp.route("/templates/<int:template_id>/cv/jobs")
@login_required
def tpl_cv_jobs(template_id: int):
    """Должности и компании, логически связанные с профессией."""
    from services import cv_gen
    code = (request.args.get("code") or "").strip()
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
        "titles": cv_gen.titles_for(code),
        "companies": [{"name": c.get("name"), "sector": c.get("sector"),
                       "sector_ru": (cv_gen.load_links_ru().get('sector_names') or {}).get(c.get("sector"), '')}
                      for c in cv_gen.companies_for(code)],
        "sectors": secs,
    })


@bp.route("/templates/<int:template_id>/cv/roll_job", methods=["POST"])
@login_required
def tpl_cv_roll_job(template_id: int):
    """Подобрать должность, компанию и обязанности — согласованно с профессией."""
    from services import cv_gen
    raw = request.get_json(silent=True) or {}
    code = (raw.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "выберите профессию"})
    level = (raw.get("level") or "medium").strip() or "medium"
    return jsonify(cv_gen.random_job(code, level))


@bp.route("/templates/<int:template_id>/cv/job_duties", methods=["POST"])
@login_required
def tpl_cv_job_duties(template_id: int):
    """Обязанности под выбранную пару «должность + компания» (без выдумок)."""
    from services import cv_gen
    raw = request.get_json(silent=True) or {}
    code = (raw.get("code") or "").strip()
    sector = (raw.get("sector") or "").strip()
    level = (raw.get("level") or "medium").strip() or "medium"
    if not code:
        return jsonify({"ok": False, "error": "выберите профессию"})
    return jsonify({"ok": True, "duties": cv_gen.duties_for(code, sector, level)})


@bp.route("/templates/<int:template_id>/cv/unique", methods=["POST"])
@login_required
def tpl_cv_unique(template_id: int):
    """Уникальное описание профессии — модель, сразу с переводом и запоминанием."""
    from services import cv_gen
    raw = request.get_json(silent=True) or {}
    code = (raw.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "выберите профессию"})
    try:
        n = int(raw.get("n") or 3)
    except Exception:
        n = 3
    res = cv_gen.generate_unique_summary(code, n=n)
    if not res.get("ok"):
        return jsonify(res)
    return jsonify({"ok": True, "text": res["en"], "value": res["en"],
                    "ru": res.get("ru") or "", "profession": code, "unique": True})


@bp.route("/templates/<int:template_id>/cv/remember", methods=["POST"])
@login_required
def tpl_cv_remember(template_id: int):
    """Ручной текст администратора: перевести и запомнить (EN для документа, RU для памяти)."""
    from services import cv_gen
    raw = request.get_json(silent=True) or {}
    text = (raw.get("text") or "").strip()
    code = (raw.get("code") or "").strip()
    lang = (raw.get("lang") or "ru").strip().lower()
    if not text:
        return jsonify({"ok": False, "error": "пустой текст"})
    ru, en = "", ""
    if lang.startswith("ru"):
        got = cv_gen.translate_ru_to_en(text)
        en = got or ""
        ru = text
    else:
        ru = cv_gen.translate_en_to_ru(text) or ""
        en = text
    if not en:
        return jsonify({"ok": False, "error": "не удалось перевести текст"})
    cv_gen.remember_phrase(code or "_common", en, ru)
    return jsonify({"ok": True, "en": en, "ru": ru, "value": en})


@bp.route("/templates/<int:template_id>/preview_pdf", methods=["POST"])
@login_required
def preview_pdf(template_id: int):
    """PDF из текущих значений формы — для всплывающего окна «Посмотреть сформированный PDF».

    Ничего не сохраняем: ни значения переменных, ни правила — только собираем PDF по тому,
    что сейчас стоит в полях страницы, и отдаём ссылку на файл.
    """
    t = _template(template_id)
    if not t:
        return jsonify({"ok": False, "error": "шаблон не найден"}), 404
    raw = request.get_json(silent=True) or {}
    values = {k: str(v or "").strip() for k, v in (raw.get("values") or {}).items()}
    # Движок документа закреплён в базе: html — координатная сетка, word — DOCX-шаблон.
    # Конструктор показывает тот же документ, который потом выпустит заявка (Андрей, 16.10.2026).
    _eng = str((t or {}).get("engine") or "html").lower()
    if _eng == "word":
        from services import doc_engine, render as _render
        _name = _render.doc_filename(t["title"] or t["code"], values, code=t["code"])
        out_pdf = RENDER_DIR / (os.path.splitext(_name)[0] + ".pdf")
        res = doc_engine.build_document(t["code"], values, RENDER_DIR, engine="word", name=out_pdf.stem)
        if not res.get("ok"):
            _why = "нет word/template.docx" if not doc_engine.word_template(t["code"]).exists() else "не собрался PDF"
            return jsonify({"ok": False, "error": f"Word-документ: {_why}"}), 500
        return jsonify({"ok": True, "url": f"/templates/file/renders/{os.path.basename(res['pdf'])}",
                        "name": os.path.basename(res['pdf']),
                        "engine": "word", "missing": res.get("missing") or []})
    html_file = HTML_DIR / t["code"] / "template.html"
    if not html_file.exists():
        return jsonify({"ok": False, "error": "HTML-шаблон не сконвертирован"}), 400
    html = html_file.read_text(encoding="utf-8")
    filled = doc_render.fill(html, values, keep_unfilled=True, template_code=t["code"])
    out_pdf = RENDER_DIR / doc_render.doc_filename(t["title"] or t["code"], values, code=t["code"])
    # Те же значения → тот же документ: если PDF уже собран из этого же содержимого,
    # отдаём готовый файл, не прогоняя weasyprint заново (повторные нажатия мгновенные).
    stamp = out_pdf.with_suffix(".key")
    digest = hashlib.md5(filled.encode("utf-8")).hexdigest()
    fresh = out_pdf.exists() and stamp.exists() and stamp.read_text(encoding="utf-8").strip() == digest
    if not fresh:
        try:
            # Если для шаблона подготовлен HTML-каркас A4 — собираем по нему (координаты,
            # шрифты из оригинала, перенос как в Word). Иначе — прежним способом.
            from services import html_frame
            built = html_frame.build_pdf(t["code"], values, out_pdf)
            if not built:
                doc_render.render_pdf(filled, out_path=out_pdf)
        except Exception as exc:                        # noqa: BLE001
            return jsonify({"ok": False, "error": f"PDF не собрался: {exc}"}), 500
        try:
            stamp.write_text(digest, encoding="utf-8")
        except Exception:
            pass
    return jsonify({"ok": True, "url": f"/templates/file/renders/{out_pdf.name}",
                    "name": out_pdf.name})


@bp.route("/templates/pdfpages")
def pdfpages():
    """Произвольный PDF из data/ -> PNG-страницы для листа визора (без браузерного просмотрщика)."""
    rel = (request.args.get("path") or "").strip().lstrip("/")
    if not rel or ".." in rel:
        return "<div style='padding:20px'>Нет файла</div>"
    full = os.path.normpath(os.path.join("/opt/wolf_v2/data", rel))
    if not full.startswith("/opt/wolf_v2/data") or not os.path.exists(full):
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
    imgs = "".join(f'<img class="pdf-page-img" src="/templates/pdffile/{key}/{pg}" alt="page">' for pg in pages)
    return f'<div style="padding:10px 0">{imgs}</div>'


@bp.route("/templates/pdffile/<key>/<name>")
def pdffile(key, name):
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", key) or not re.fullmatch(r"page-?[0-9]+\.png", name):
        abort(404)
    d = f"/opt/wolf_v2/data/pdf_cache/{key}"
    if not os.path.isdir(d):
        abort(404)
    return send_from_directory(d, name)


def _manager_kind(name: str):
    """Наш ли это документ (сделан менеджером руками) и какого он типа.

    У заказчика в папке клиента на Google Диске лежит уже собранный пакет: часть файлов
    менеджер делал руками (наши письма, договоры, резюме, E-02), часть — сам клиент
    (паспорт, фото, справка банка, КИТАС). Разделяем их, чтобы «Клиент» показывал только
    документы клиента, а наши документы брались как оригинальный пример (Андрей, 06.10.2026).
    """
    n = (name or "").lower()
    rules = (
        ("statement_letter", r"e[\-_ ]?0?2\b|statement[_ ]letter|surat|^0?2[\.\s\-_]|form[\s_]*e[\s\-]*0?2"),
        ("bridging", r"bridging"),
        ("conversion", r"conversion"),
        ("d12", r"d12|cover[_ ]?letter|permohonan"),
        ("work_agreement", r"work[_ ]?agreement|remote[_ ]?work"),
        ("employment_contract", r"contract|agreement"),
        ("cv", r"resume|\bcv\b|curriculum"),
    )
    for kind, rx in rules:
        if re.search(rx, n):
            return kind
    return None


def _manager_doc_path(tpl_code: str, client_id: int | None):
    """Наш документ того же типа, сделанный менеджером для этого клиента (образец)."""
    if not client_id:
        return None
    code = (tpl_code or "").lower()
    want = None
    for kind in ("statement_letter", "bridging", "conversion", "d12", "work_agreement",
                 "employment_contract", "cv"):
        if code.startswith(kind) or kind in code:
            want = kind
            break
    if want is None:
        return None
    for f in _client_files_of(client_id):
        if _manager_kind(f.name) == want:
            return str(f)
    return None


def _client_files_of(client_id: int):
    """Файлы пакета клиента из кэша Google Диска (по убыванию свежести имени)."""
    from pathlib import Path as _P
    folder = _P("/opt/wolf_v2/data/gdrive_cache") / ("client_%s" % client_id)
    if not folder.is_dir():
        return []
    out = []
    for f in sorted(folder.iterdir()):
        if not f.is_file() or f.name.startswith(("~$", ".")):
            continue
        if f.suffix.lower() not in (".pdf", ".jpg", ".jpeg", ".png", ".webp"):
            continue
        out.append(f)
    return out


def _client_original_path(tpl_code: str, client_id: int | None):
    """Реальный документ этого клиента, подходящий по типу к шаблону.

    Требование Андрея (06.10.2026): «Оригинальный пример» в конструкторе продукта должен
    быть документом ТОГО ЖЕ клиента и того же типа — для визы C1 это его банковская
    справка, для E-02 — уже сделанный менеджером E-02, а не чужой образец.
    """
    if not client_id:
        return None
    # 1) наш документ, сделанный менеджером для этого клиента (письма, договоры, резюме)
    _mgr = _manager_doc_path(tpl_code, client_id)
    if _mgr:
        return _mgr
    # 2) документ клиента (банковская справка, паспорт, фото, КИТАС и прочее)
    code = (tpl_code or "").lower()
    rules = (
        ("bank_statement", r"bank|statement|выписка"),
        ("passport", r"pas+port|paspor|паспорт"),
        ("cv__", r"resume|_cv\b|cv[_\.]"),
        ("itk", r"\bitk\b|kitas"),
        ("photo", r"photo|foto"),
        ("d12", r"d12|permohonan|cover[_ ]?letter"),
        ("statement_letter", r"e[\-_ ]?0?2|statement[_ ]letter|surat"),
    )
    pat = None
    for key, rx in rules:
        if key in code:
            pat = re.compile(rx, re.I)
            break
    if pat is None:
        # Тип документа не опознан (например, MOU или иное): чужой файл вместо примера
        # не подставляем — лучше пусто, чем не тот документ (Андрей, 06.10.2026).
        return None
    files = [f for f in _client_files_of(client_id) if pat.search(f.name)]
    if not files:
        return None
    files.sort(key=lambda p: (p.suffix.lower() != ".pdf", ".photo." in p.name, p.name.lower()))
    return str(files[0])


@bp.route("/templates/htmlview/<int:template_id>")
@login_required
def htmlview(template_id: int):
    """Собранный HTML документа для конкретной заявки — то, что видно в окне сравнения справа.

    Отдаём серверный рендер (тот же движок, что печатает PDF), поэтому переносы, кегль и
    позиции совпадают с бумагой: в визоре не может быть наложений и «уползания» за край.
    """
    t = db.q1("SELECT id, code FROM templates WHERE id=?", (template_id,))
    if not t:
        abort(404)
    app_id = request.args.get("app", type=int)
    code = t["code"]
    from services import html_frame
    if not html_frame.available(code):
        abort(404)
    vals = html_frame.values_with_frames(code, {}, app_id)
    # Приоритет — рабочий HTML-шаблон документа: он несёт подложку и шрифты внутри себя
    # (base64), поэтому в визоре видны логотип, печать и подпись, и документ совпадает с бумагой.
    tpl = HTML_DIR / code / "template.html"
    if tpl.exists():
        raw = tpl.read_text(encoding="utf-8")
        if "{{" in raw:
            import html as _h
            import re as _re

            def _val(m):
                v = vals.get(m.group(1))
                return _h.escape(str(v)) if v is not None else ""
            body = _re.sub(r"\{\{\s*(\w+)\s*\}\}", _val, raw)
            body = body.replace(
                "</head>",
                "<style>html,body{background:#E7EBEE}"
                ".sheet{margin:0 auto;box-shadow:0 2px 10px rgba(0,0,0,.12)}</style></head>", 1)
            # Масштаб по ширине окна: в окне сравнения документ должен быть виден целиком,
            # без горизонтальной прокрутки (лист — 595.28pt = 793.7px при 96 dpi).
            body = body.replace(
                "</body>",
                "<script>(function(){var q=new URLSearchParams(location.search);"
                "if(!q.get('fit'))return;function fit(){var s=document.querySelector('.sheet');"
                "if(!s)return;var k=Math.min(1,(document.documentElement.clientWidth-18)/793.7);"
                "s.style.transformOrigin='top left';s.style.transform='scale('+k+')';"
                "document.body.style.height=(1122.5*k+24)+'px';}"
                "fit();window.addEventListener('resize',fit);})();</script></body>", 1)
            return body
    m = html_frame._flow()
    layout = m.build_layout(code, dict(vals))
    body = m.render_html(code, layout)
    base = '<base href="/templates/file/html/%s/">' % code
    body = body.replace("<head>", "<head>" + base, 1)
    body = body.replace("</head>",
                        "<style>html,body{background:#E7EBEE}"
                        ".sheet{margin:0 auto;box-shadow:0 2px 10px rgba(0,0,0,.12)}</style></head>", 1)
    return body


def _compare_without_app(t, template_id: int, ctx_line: str):
    """Сравнение без заявки (конструктор документов): слева эталон шаблона, справа наша сборка.

    Правый лист собирает тот же движок, что выпускает документы: html — координаты,
    word — DOCX-шаблон. Так в конструкторе видно ровно то, что уйдёт клиенту.
    """
    import html as _hp
    from services import doc_engine
    code = t["code"]
    vals = {}
    try:
        from services.previews import _example_values
        vals = _example_values(template_id) or {}
    except Exception:
        vals = {}
    ours_err = ""
    ours_rel = ""
    try:
        res = doc_engine.build_document(code, vals, RENDER_DIR, name="cmp_%s" % code)
        if res.get("pdf"):
            ours_rel = os.path.relpath(res["pdf"], "/opt/wolf_v2/data")
    except Exception as exc:                              # noqa: BLE001
        ours_err = str(exc)[:200]
    if not ours_rel:
        ours_err = ours_err or "наш документ не собрался"
    orig_file = HTML_DIR / code / "example_filled.pdf"
    eng = (doc_engine.engine_of(code) or "html").upper()
    left = (f'<iframe src="/templates/pdfview/{template_id}?kind=clean&fit=1"></iframe>' if orig_file.exists()
            else '<div style="padding:20px;color:#B91C1C">Эталон не найден</div>')
    right = (f'<iframe src="/templates/pdfview/{template_id}?kind=built&fit=1"></iframe>' if ours_rel
             else f'<div style="padding:20px;color:#B91C1C">Готовый документ: {_hp.escape(ours_err)}</div>')
    sync_js = ('<script>(function(){'
               'var fr=[].slice.call(document.querySelectorAll(".cmp-col iframe"));'
               'if(fr.length<2)return;'
               'window.addEventListener("message",function(e){'
               '  var d=e.data||{};if(d.t!=="cmp-scroll")return;'
               '  fr.forEach(function(f){if(f.contentWindow!==e.source){'
               '    try{f.contentWindow.postMessage(d,"*");}catch(x){}}});'
               '});'
               '})();</script>')
    return (
        '<style>'
        '.cmp-wrap{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:12px;height:100vh;box-sizing:border-box}'
        '.cmp-col{background:#fff;border:1px solid #E1E7E3;border-radius:10px;overflow:hidden;display:flex;flex-direction:column}'
        '.cmp-head{padding:8px 12px;font-weight:700;font-size:13px;background:#F4FAF6;color:#166534;'
        'border-bottom:1px solid #E1E7E3}'
        '.cmp-head span{font-weight:400;color:#64748B;font-size:11.5px}'
        '.cmp-col .cmp-body{flex:1;overflow:hidden;background:#E7EBEE}'
        '.cmp-col .cmp-body iframe{width:100%%;height:100%%;border:0;display:block}'
        '</style>'
        '<div class="cmp-title" style="padding:8px 14px;font-size:13.5px;font-weight:700;color:#14532D;background:#fff;'
        'border-bottom:1px solid #E1E7E3">%s</div>'
        '<div class="cmp-wrap">'
        '<div class="cmp-col"><div class="cmp-head">Оригинал <span>%s</span></div>'
        '<div class="cmp-body">%s</div></div>'
        '<div class="cmp-col"><div class="cmp-head">Наш документ (%s) <span>собран шаблоном</span></div>'
        '<div class="cmp-body">%s</div></div>'
        '</div>'
        % (_hp.escape(ctx_line), _hp.escape(orig_file.name), left, eng, right)) + sync_js


@bp.route("/templates/compare/<int:template_id>")
@login_required
def compare(template_id: int):
    """Сравнение листов: слева оригинал клиента, справа сборка системы.

    Требование Андрея (06.10.2026): нужно визуально проверять, насколько то, что собрала
    система, совпадает с оригиналом — и иметь этот механизм под рукой в конструкторе.
    """
    t = db.q1("SELECT id, code, title FROM templates WHERE id=?", (template_id,))
    if not t:
        abort(404)
    import html as _hp
    app_id = request.args.get("app", type=int)
    # Что именно сравниваем: продукт · заявка · документ (требование Андрея, 06.10.2026).
    # Продукт берём из конструктора (product=), а не из заявки: документ открыт в пакете того
    # продукта, в котором администратор работает.
    _ctx = []
    _pid_arg = request.args.get("product", type=int)
    _prod = None
    if _pid_arg:
        _prod = db.q1("SELECT id, code, name FROM products WHERE id=?", (_pid_arg,))
    if not _prod and app_id:
        _prod = db.q1("SELECT p.id, p.code, p.name FROM products p "
                      "JOIN applications a ON a.product_id = p.id WHERE a.id=?", (app_id,))
    if _prod:
        _ctx.append('Конструктор продукта «%s»'
                    % (SHORT_NAME.get(_prod.get("code"), _prod.get("name") or _prod.get("code") or "")))
    if app_id:
        _ctx.append('Заявка №%s' % app_id)
    if _prod:
        _seq = [r["id"] for r in db.q(
            """SELECT t.id FROM product_documents pd JOIN templates t ON t.id=pd.template_id
               WHERE pd.product_id=? AND COALESCE(t.status,'ok') NOT IN ('merged','hidden')
               ORDER BY pd.sort_order, COALESCE(t.doc_index,999), t.title""", (_prod["id"],)) or []]
        if template_id in _seq:
            _ctx.append('Документ №%s — %s' % (_seq.index(template_id) + 1, t["title"] or ""))
        else:
            _ctx.append('Документ вне пакета — %s' % (t["title"] or ""))
    _ctx_line = " · ".join(_ctx) or ("Документ: " + (t["title"] or ""))
    if not app_id:
        # Конструктор документов: заявки нет — сравниваем эталон шаблона с нашей сборкой.
        body = _compare_without_app(t, template_id, _ctx_line)
        if request.args.get("embed"):
            return ('<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">'
                    '<title>Сравнение</title></head><body style="margin:0;background:#E7EBEE">'
                    + body + '</body></html>')
        return render("Сравнение: " + (t["title"] or ""), "templates", body)
    app_row = db.application_get(app_id) if app_id else None
    cid = int(app_row["client_id"]) if app_row else None
    cname = ""
    if cid:
        cl = db.client_get(cid) or {}
        cname = ("%s %s" % (cl.get("surname") or "", cl.get("name") or "")).strip()
    orig = _client_original_path(t["code"], cid) or ""
    orig_name = os.path.basename(orig) if orig else "оригинал не найден"
    ours_note = ("заявка №%s · %s" % (app_id, cname)) if app_id else "нет заявки"
    body = (
        '<style>'
        '.cmp-wrap{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:12px}'
        '.cmp-col{background:#fff;border:1px solid #E1E7E3;border-radius:10px;overflow:hidden;'
        'display:flex;flex-direction:column}'
        '.cmp-head{padding:8px 12px;font-weight:700;font-size:13px;background:#F4FAF6;color:#166534;'
        'border-bottom:1px solid #E1E7E3;display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}'
        '.cmp-head span{font-weight:400;color:#64748B;font-size:11.5px}'
        '.cmp-title{padding:10px 14px;font-size:13.5px;font-weight:700;color:#14532D;background:#fff;'
        'border-bottom:1px solid #E1E7E3}'
        '.cmp-col iframe{width:100%%;height:90vh;border:0;background:#E7EBEE;display:block}'
        '@media(max-width:900px){.cmp-wrap{grid-template-columns:1fr}}'
        '</style>'
        '<div class="cmp-title">%s</div>'
        '<div class="cmp-wrap">'
        '<div class="cmp-col"><div class="cmp-head">Оригинал клиента'
        '<span>%s</span></div><iframe src="/templates/pdfview/%s?kind=client%s&fit=1"></iframe></div>'
        '<div class="cmp-col"><div class="cmp-head">Сборка системы (HTML)'
        '<span>%s</span></div><iframe src="/templates/htmlview/%s?app=%s&fit=1"></iframe></div>'
        '</div>'
        % (_hp.escape(_ctx_line), _hp.escape(orig_name), template_id, cid or 0,
           _hp.escape(ours_note), template_id, app_id or 0))
    if request.args.get("embed"):
        # Внутри модального слоя конструктора: отдаём только сравнение, без каркаса сайта.
        # Прокрутка двух окон синхронизирована (сообщения от панелей пересылаем друг другу).
        return ('<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">'
                '<title>Сравнение</title>'
                '<style>.cmp-wrap{padding:8px;height:100vh;box-sizing:border-box}'
                '.cmp-col iframe{height:calc(100vh - 62px)}</style>'
                '</head><body style="margin:0;background:#E7EBEE">'
                + body +
                '<script>(function(){'
                'var fr=[].slice.call(document.querySelectorAll(".cmp-col iframe"));'
                'if(fr.length<2)return;'
                'window.addEventListener("message",function(e){'
                '  var d=e.data||{};if(d.t!=="cmp-scroll")return;'
                '  fr.forEach(function(f){if(f.contentWindow!==e.source){'
                '    try{f.contentWindow.postMessage(d,"*");}catch(x){}}});'
                '});'
                '})();</script>'
                '</body></html>')
    return render("Сравнение: " + (t["title"] or ""), "templates", body)


@bp.route("/templates/pdfview/<int:template_id>")
def pdfview(template_id):
    """Страницы PDF картинками — вставляются в лист визора (масштаб не ломается)."""
    kind = request.args.get("kind", "marked")
    t = db.q1("SELECT id, code, source_pdf FROM templates WHERE id=?", (template_id,))
    if not t:
        return "<div style='padding:20px'>Шаблон не найден</div>"
    code = t["code"]
    import html as _hp
    if kind.startswith("client"):
        # «Оригинальный пример» — реальный документ этого же клиента того же типа.
        _cid = request.args.get("client", type=int)
        if not _cid and kind[6:].isdigit():
            _cid = int(kind[6:])
        src = _client_original_path(code, _cid) or ""
        names = {}
    elif kind.startswith("ours"):
        # Наша сборка: документ, который система сделала по заявке (для сравнения с оригиналом).
        _app = request.args.get("app", type=int)
        if not _app and kind[4:].isdigit():
            _app = int(kind[4:])
        if not _app:
            return "<div style='padding:20px'>Не указана заявка</div>"
        from services import render as _render
        cache_dir = Path(f"/opt/wolf_v2/data/cache/compare/{code}_ours{_app}")
        cache_dir.mkdir(parents=True, exist_ok=True)
        src = str(cache_dir / f"{code}.pdf")
        try:
            _render.generate(_app, template_id, out_path=src)
        except Exception as exc:  # noqa: BLE001
            return ("<div style='padding:20px;color:#B91C1C'>Не удалось собрать документ: "
                    + _hp.escape(str(exc)[:200]) + "</div>")
        names = {}
    elif kind.startswith("built"):
        # Наш документ для сравнения в конструкторе (без заявки): собираем тем движком,
        # который закреплён за шаблоном — html или word (Андрей, 16.10.2026).
        from services import doc_engine
        _vals = {}
        try:
            from services.previews import _example_values
            _vals = _example_values(template_id) or {}
        except Exception:
            _vals = {}
        cache_dir = Path(f"/opt/wolf_v2/data/cache/compare/{code}_built")
        cache_dir.mkdir(parents=True, exist_ok=True)
        src = str(cache_dir / f"{code}.pdf")
        try:
            res = doc_engine.build_document(code, _vals, str(cache_dir), name=code)
            src = res.get("pdf") or src
        except Exception as exc:                          # noqa: BLE001
            return ("<div style='padding:20px;color:#B91C1C'>Не удалось собрать документ: "
                    + _hp.escape(str(exc)[:200]) + "</div>")
        names = {}
    else:
        names = {
            "marked": f"/opt/wolf_v2/data/templates/{code}/example_marked.pdf",
            "clean": f"/opt/wolf_v2/data/templates/{code}/example_filled.pdf",
            "source": str(SOURCES_DIR / (t["source_pdf"] or "")),
        }
        src = names.get(kind) or ""
    if not src or not os.path.exists(src):
        return "<div style='padding:20px;color:#6B7C70'>Для этого документа нет подходящего PDF.</div>"
    cache = f"/opt/wolf_v2/data/pdf_cache/{code}_{kind}"
    os.makedirs(cache, exist_ok=True)
    # Перерисовываем страницы, если исходный PDF новее кэша: после правки значения переменной
    # в сборке должно быть видно новое значение, а не старая картинка (Андрей, 06.10.2026).
    _pngs = [f for f in os.listdir(cache) if f.endswith(".png")]
    _stale = not _pngs
    if _pngs and src and os.path.exists(src):
        try:
            _stale = os.path.getmtime(src) > min(os.path.getmtime(os.path.join(cache, f)) for f in _pngs) - 1
        except Exception:
            _stale = True
    if _stale:
        # Замок: два окна сравнения открываются одновременно и рендерят одну и ту же сборку.
        # Без замка они затирали картинки друг другу — правая панель оставалась пустой.
        import fcntl
        import shutil
        lock_path = f"/opt/wolf_v2/data/pdf_cache/.{code}_{kind}.lock"
        with open(lock_path, "w") as _lk:
            fcntl.flock(_lk, fcntl.LOCK_EX)
            _pngs = [f for f in os.listdir(cache) if f.endswith(".png")]
            _need = not _pngs
            if _pngs and src and os.path.exists(src):
                try:
                    _need = os.path.getmtime(src) > min(os.path.getmtime(os.path.join(cache, f))
                                                         for f in _pngs) - 1
                except Exception:
                    _need = True
            if _need:
                tmp = cache + ".tmp"
                shutil.rmtree(tmp, ignore_errors=True)
                os.makedirs(tmp, exist_ok=True)
                subprocess.run(["/usr/bin/pdftoppm", "-r", "96", "-png", src, os.path.join(tmp, "page")],
                               timeout=120, check=False)
                for f in sorted(os.listdir(tmp)):
                    if f.endswith(".png"):
                        os.replace(os.path.join(tmp, f), os.path.join(cache, f))
                shutil.rmtree(tmp, ignore_errors=True)
    pages = sorted(f for f in os.listdir(cache) if f.endswith(".png"))
    if not pages:
        return "<div style='padding:20px;color:#B91C1C'>Не удалось отрендерить PDF.</div>"
    imgs = "".join(f'<img class="pdf-page-img" src="/templates/pdfimg/{code}/{kind}/{pg}" alt="page">' for pg in pages)
    if request.args.get("fit"):
        # Режим сравнения: лист вписан ПО ШИРИНЕ окна, высота прокручивается;
        # прокрутка двух окон синхронизируется через postMessage (Андрей, 06.10.2026).
        return ('<style>html,body{margin:0;padding:0;background:#E7EBEE;height:100%}'
                '.fit-wrap{height:100vh;overflow-x:hidden;overflow-y:auto;padding:6px 8px 20px;'
                'box-sizing:border-box}'
                '.pdf-page-img{width:100%;max-width:100%;height:auto;margin:0 auto 10px;display:block;'
                'background:#fff}</style>'
                '<div class="fit-wrap" id="fit-wrap">' + imgs + '</div>'
                '<script>'
                '(function(){'
                'var w=document.getElementById("fit-wrap");if(!w)return;'
                'var guard=0;'
                'w.addEventListener("scroll",function(){'
                '  if(Date.now()<guard)return;'
                '  var m=w.scrollHeight-w.clientHeight;'
                '  try{parent.postMessage({t:"cmp-scroll",p:(m>0?w.scrollTop/m:0)}, "*");}catch(e){}'
                '},{passive:true});'
                'window.addEventListener("message",function(e){var d=e.data||{};if(d.t!=="cmp-scroll")return;'
                '  var m=w.scrollHeight-w.clientHeight;guard=Date.now()+150;w.scrollTop=(d.p||0)*m;});'
                '})();'
                '</script>')
    return f'<div style="padding:10px 0">{imgs}</div>'


@bp.route("/templates/pdfimg/<code>/<kind>/<name>")
def pdfimg(code, kind, name):
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", kind) or not re.fullmatch(r"page-?[0-9]+\.png", name):
        abort(404)
    d = f"/opt/wolf_v2/data/pdf_cache/{code}_{kind}"
    if not os.path.isdir(d):
        abort(404)
    return send_from_directory(d, name)


@bp.route("/templates/file/<path:subpath>")
@login_required
def file(subpath: str):
    mapping = {
        "previews": pdf2html.PREVIEW_DIR,
        "html": HTML_DIR,
        "renders": RENDER_DIR,
        "sources": SOURCES_DIR,
        "templates": str(BASE_DIR / "data" / "templates"),
    }
    for root, base in mapping.items():
        if subpath.startswith(root + "/"):
            return send_from_directory(base, subpath[len(root) + 1:], as_attachment=False)
    abort(404)
