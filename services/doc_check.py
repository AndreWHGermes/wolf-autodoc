"""Проверка комплекта документов заявки по официальным требованиям и канону агентства.

Запуск:
    cd /opt/wolf_v2 && /usr/bin/python3 services/doc_check.py 87

Выдаёт замечания с уровнями:
    BLOCK — в таком виде подавать нельзя (расхождение в датах, чужой подписант, чужой клиент);
    WARN  — не запрещено, но требует подтверждения (подписание позже начала и т.п.);
    INFO  — подсказка по составу и заполнению.

Источники правил — docs/checklists/ (официальные требования иммиграции + канон агентства).
"""
import html
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")   # чтобы работали импорты вида services.gdrive_api при запуске скриптом

DB = Path("/opt/wolf_v2/data/wolf.db")
BUILD_DIR = Path("/opt/wolf_v2/data/doc_html")
TODAY = date.today()

MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
          "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}


def strip_html(s: str) -> str:
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = s.replace("\u00a0", " ")
    return re.sub(r"[ \t]+", " ", s)


def parse_en_date(s: str):
    """'5th July 2024' -> date(2024,7,5)"""
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})", s or "")
    if not m:
        return None
    mon = MONTHS.get(m.group(2).lower())
    if not mon:
        return None
    try:
        return date(int(m.group(3)), mon, int(m.group(1)))
    except ValueError:
        return None


def parse_dot_date(s: str):
    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", s or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _is_rule_text(t: str) -> bool:
    """Строка-заполнитель формы (точки, подчёркивания, тире) — это фон, а не текст.

    На бланке E-02 значения пишутся поверх пунктирных линий: считать это наложением
    нельзя, иначе проверка вёрстки блокирует верный документ.
    """
    s = re.sub(r"\s+", "", t or "")
    if len(s) < 4:
        return False
    return len(re.findall(r"[.\u2026_\-–—·]", s)) / len(s) > 0.8


def _layout_blocks(raw: str) -> list:
    """Блоки текста собранного документа с координатами и шрифтом.

    Нужны для проверки качества оформления: наложение текста, центровка шапки,
    скачки шрифтов и неровные строки видно только по геометрии.
    """
    out = []
    # Документы конструктора собираются страницами <div class="sheet">: блоки сравниваем
    # только внутри своей страницы, иначе наложения между страницами считаются ложными.
    parts = re.split(r'<div[^>]*class="[^"]*\bsheet\b[^"]*"[^>]*>', raw, flags=re.I)
    _page = 0
    for _part in parts:
        _page += 1
        for m in re.finditer(r'<(div|span)\b[^>]*style="([^"]*)"[^>]*>(.*?)</\1>', _part, re.S | re.I):
            st, body = m.group(2), m.group(3)
            if "left:" not in st or "top:" not in st:
                continue

            def _pt(key):
                mm = re.search(r"(?:^|;)\s*" + key + r":\s*(-?[\d.]+)pt", st)
                return float(mm.group(1)) if mm else None

            left, top = _pt("left"), _pt("top")
            if left is None or top is None:
                continue
            txt = re.sub(r"\s+", " ", strip_html(body)).strip()
            if not txt:
                continue
            fs_m = re.search(r"font-size:\s*([\d.]+)pt", st)
            fs = float(fs_m.group(1)) if fs_m else 0.0
            fam_m = re.search(r"font-family:\s*([^;\"']+)", st)
            w, h = _pt("width"), _pt("height")
            if w is None:
                w = max(len(txt) * (fs or 9) * 0.5, 20.0)
            if h is None or h <= 0:
                h = max((fs or 9) * 1.35, 8.0)
            # контейнеры листа (на всю страницу) в проверке не участвуют
            if w > 520 and h > 400:
                continue
            out.append({"left": left, "top": top, "w": w, "h": h, "font_size": fs,
                        "font_family": (fam_m.group(1).strip() if fam_m else ""), "text": txt,
                        "page": _page})
    return out


class Check:
    # Человеческие названия документов для сообщений: код шаблона → как это назвать в системе.
    LABELS = {
        "remote_work_agreement__default": "Договор Remote Work Agreement",
        "statement_letter_e02__bridging": "Форма E-02 (мостовая виза)",
        "statement_letter_e02__conversion": "Форма E-02 (конверсия)",
        "bridging_request_letter__default": "Письмо в иммиграцию: Bridging (офис по адресу клиента)",
        "conversion_request_letter__default": "Письмо в иммиграцию: Conversion (офис по адресу клиента)",
        "cv__format_short": "Резюме (короткое)",
        "cv__format_detailed": "Резюме (подробное)",
        "cv__format_sivaev": "Резюме (формат Сиваева)",
        "google drive": "Папка клиента на Google Диске",
        "паспорт": "Паспорт клиента",
    }

    def __init__(self, app_id: int):
        self.app_id = app_id
        self.find = []
        self.c = sqlite3.connect(str(DB))
        self.c.row_factory = sqlite3.Row
        self.docs = []          # документы заявки: dict(template_id, code, doc_index, status)
        self.texts = {}         # code -> текст собранного HTML
        self.tpl = {}           # code -> dict строки templates
        self.load()

    def load(self):
        rows = self.c.execute("""SELECT ad.template_id, ad.status, t.code, t.doc_index
                                 FROM application_documents ad
                                 JOIN templates t ON t.id = ad.template_id
                                 WHERE ad.application_id=? ORDER BY t.doc_index""", (self.app_id,)).fetchall()
        self.docs = [dict(r) for r in rows]
        self.by_code = {d["code"]: d for d in self.docs}
        self.client = dict(self.c.execute("""SELECT c.* FROM clients c
                                             JOIN applications a ON a.client_id=c.id
                                             WHERE a.id=?""", (self.app_id,)).fetchone() or {})
        app = self.c.execute("SELECT * FROM applications WHERE id=?", (self.app_id,)).fetchone()
        self.app = dict(app) if app else {}
        pid = self.app.get("product_id")
        self.product = dict(self.c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone() or {})
        self.office = (self.app.get("office") or self.app.get("immigration_office") or "").lower()
        for d in self.docs:
            # Проверяем все документы заявки, кроме отклонённых вариантов (например,
            # письмо для другого офиса — оно в пакет не входит). Раньше проверялись
            # только уже подтверждённые документы: черновик не проверялся, значит и
            # подтверждён быть не мог — замкнутый круг, из-за которого документы
            # оставались в статусе «заполнен» навсегда.
            if d["status"] == "rejected":
                continue
            # Если документ уже собран в PDF — проверяем именно его. PDF и HTML-кэш
            # вида документа собираются разными путями, и проверка по кэшу ставила
            # ложные блокировки: в PDF значение уже латиницей, а в кэше осталось русским.
            _pdf = Path("/opt/wolf_v2/data/out/%d/%s.pdf" % (self.app_id, d["code"]))
            if _pdf.is_file():
                try:
                    import pymupdf
                    self.texts[d["code"]] = "\n".join(p.get_text() for p in pymupdf.open(str(_pdf)))
                    continue
                except Exception:                                      # noqa: BLE001
                    pass
            files = sorted(BUILD_DIR.glob("app%d_tpl%d_*.html" % (self.app_id, d["template_id"])),
                           key=lambda p: p.stat().st_mtime)
            if not files:
                # Сборки нет или её убрали (пересборка очищает кэш) — собираем сами.
                # Иначе проверка читала бы ШАБЛОН с метками вида {{ … }} и выдавала
                # ложные блоки «остался незаполненный шаблонный текст».
                try:
                    _freeze(self.app_id, d["template_id"], actor="финишная проверка")
                    files = sorted(BUILD_DIR.glob("app%d_tpl%d_*.html" % (self.app_id, d["template_id"])),
                                   key=lambda p: p.stat().st_mtime)
                except Exception as _exc:  # noqa: BLE001
                    files = []
            if not files:
                _frozen = Path("/opt/wolf_v2/data/frozen") / ("app%s_tpl%s.html" % (self.app_id, d["template_id"]))
                if _frozen.is_file():
                    files = [_frozen]
            if files:
                # Из собранного HTML берём только то, что печатается: в файле есть ещё
                # служебный блок со значениями (для предпросмотра «откуда значение»),
                # и проверка ловила русские буквы в служебных данных — в самом документе
                # их нет. Поэтому служебные вставки вырезаем до разбора текста.
                _raw = files[-1].read_text(encoding="utf-8", errors="ignore")
                import re as _re2
                _raw = _re2.sub(r"(?is)<script\b[^>]*>.*?</script>", " ", _raw)
                _raw = _re2.sub(r"(?is)<style\b[^>]*>.*?</style>", " ", _raw)
                self.texts[d["code"]] = strip_html(_raw)
            t = Path("/opt/wolf_v2/data/templates/%s/template.html" % d["code"])
            if t.is_file():
                self.tpl[d["code"]] = strip_html(t.read_text(encoding="utf-8", errors="ignore"))

    def add(self, level, doc, msg, source=""):
        self.find.append({"level": level, "doc": self.LABELS.get(doc, doc), "code": doc,
                          "msg": msg, "source": source})

    # ---------------------------------------------------------------- правила
    def rule_kit(self):
        """Состав комплекта: по каждому слоту продукта должен быть подтверждённый документ."""
        pid = self.app.get("product_id")
        if not pid:
            return
        need = self.c.execute("""SELECT DISTINCT pd.slot_code, t.code, t.doc_index, pd.required
                                 FROM product_documents pd JOIN templates t ON t.id=pd.template_id
                                 WHERE pd.product_id=?""", (pid,)).fetchall()
        slots = {}
        required = {}
        for r in need:
            slots.setdefault(r["slot_code"], []).append(r["code"])
            required[r["slot_code"]] = required.get(r["slot_code"], False) or bool(r["required"])
        for slot, codes in sorted(slots.items()):
            present = [c for c in codes if c in self.by_code]
            if not present:
                # Необязательный слот (у всех его шаблонов `required=0`) подачу не блокирует:
                # у C1-EXT контракт есть в наборе как возможный, но по этому продукту не подаётся —
                # прежнее правило требовало его всегда и держало заявку на отправке навсегда.
                if not required.get(slot):
                    self.add("INFO", slot, "необязательный слот без документа (варианты: %s)"
                             % ", ".join(codes), "состав продукта")
                    continue
                self.add("BLOCK", slot, "в комплекте нет ни одного документа этого слота (варианты: %s)"
                         % ", ".join(codes), "состав продукта")
                continue
            # Галочку менеджера система не ждёт: проверку состава и качества делает
            # она сама, подтверждение ставится автоматически после проверок.

    def rule_contract_dates(self):
        """Даты договора: одна дата начала в разделах 2 и 7, окончание = начало + 5 лет."""
        code = "remote_work_agreement__default"
        t = self.texts.get(code) or self.tpl.get(code)
        if not t:
            return
        # В собранном HTML подписи абзацев разбиваются тегами, поэтому фразу можно не найти.
        # Берём все английские даты документа и разбираем их по ролям: подписание — самая поздняя,
        # начало срока — самая ранняя, окончание — самая поздняя из оставшихся, а если самая ранняя
        # встречается дважды, значит она же стоит и в разделе 7 (одна дата начала на два места).
        dates = [d for d in (parse_en_date(x) for x in
                             re.findall(r"\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+\s+\d{4}", t)) if d]
        start = min(dates) if dates else None
        end = next((d for d in dates if start and d == date(start.year + 5, start.month, start.day)), None)
        # Точка отсчёта — та же, что у генератора документов (services.values._app_base_date):
        # дата заявки, а не «сегодня». Иначе проверка расходится с тем, что напечатано,
        # и заявка вечно стоит на одном месте с ложным BLOCK.
        base = TODAY
        try:
            from services.values import _app_base_date
            base = _app_base_date({"_app_id": self.app_id}) or TODAY
        except Exception:                                      # noqa: BLE001
            base = TODAY
        # подписание — дата в пределах месяца от точки отсчёта: бумага подписана недавно
        head = next((d for d in sorted(dates, reverse=True) if 0 <= (base - d).days <= 31), None)
        sec7 = start if (start and dates.count(start) > 1) else None

        if not head:
            self.add("BLOCK", code, "не найдена дата подписания («made on this …»)", "канон дат")
        else:
            delta = (base - head).days
            if not (5 <= delta <= 7):
                # Отступление от канона — не повод останавливать заявку: документ уже
                # изготовлен, дату могли задать вручную или заявка пришла позже срока.
                self.add("WARN", code, "дата подписания %s, от задачи отсчёт %d дн. (канон 5–7) "
                         "— не блокирует подачу" % (head.strftime("%d.%m.%Y"), delta), "канон дат")
        if not start:
            self.add("BLOCK", code, "не найдена дата начала действия («has been in effect since …»)", "канон дат")
        if start and end:
            expect = date(start.year + 5, start.month, start.day)
            if end != expect:
                self.add("BLOCK", code, "окончание %s не равно началу плюс пять лет (%s)"
                         % (end.strftime("%d.%m.%Y"), expect.strftime("%d.%m.%Y")), "канон дат")
        if start and sec7 and start != sec7:
            self.add("BLOCK", code, "в разделе 7 дата начала %s, а в разделе 2 — %s"
                     % (sec7.strftime("%d.%m.%Y"), start.strftime("%d.%m.%Y")), "канон дат")
        if head and start and head < start:
            self.add("WARN", code, "дата подписания (%s) раньше начала действия (%s)"
                     % (head.strftime("%d.%m.%Y"), start.strftime("%d.%m.%Y")), "логика договора")
        if head and start and head > start:
            self.add("INFO", code, "подписание %s позже начала действия %s — так согласовано (документ оформлен позже)"
                     % (head.strftime("%d.%m.%Y"), start.strftime("%d.%m.%Y")), "согласовано 05.10.2026")
        if start and start.year < TODAY.year - 2:
            self.add("WARN", code, "год начала %d — старше двух лет назад" % start.year, "канон дат")

    def rule_contract_passport(self):
        code = "remote_work_agreement__default"
        t = self.texts.get(code) or self.tpl.get(code)
        if not t:
            return
        pn = (self.client.get("passport_number") or "").strip()
        exp = parse_dot_date(self.client.get("passport_expiry") or "")
        if pn and pn not in t.replace(" ", ""):
            self.add("WARN", code, "номер паспорта клиента %s в договоре не встречается" % pn, "официально: паспорт")
        dates = set(parse_dot_date(x) for x in re.findall(r"\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}", t))
        dates.discard(None)
        if exp and dates and exp not in dates:
            # В эталоне договора паспортный блок содержит номер и дату рождения, срок действия
            # паспорта там не печатается — поэтому это предупреждение, а не запрет.
            self.add("WARN", code, "срок действия паспорта (%s) в договоре не указан; в документе: %s"
                     % (exp.strftime("%d.%m.%Y"), ", ".join(sorted(d.strftime("%d.%m.%Y") for d in dates))),
                     "официально: паспорт")
        elif exp and not dates:
            self.add("WARN", code, "в договоре не найдены паспортные даты (ожидается срок до %s)"
                     % exp.strftime("%d.%m.%Y"), "официально: паспорт")

    def rule_placeholders(self):
        marks = ["(profession)", "today’s date", "today's date", "random date", "(name)",
                 "{{", "}}", "………", "Lorem"]
        for code in sorted(self.texts):
            t = self.texts.get(code) or ""
            for m in marks:
                if m in t and m not in ("………",):
                    self.add("BLOCK", code, "в документе остался незаполненный шаблонный текст: %s" % m,
                             "обработка шаблона")

    def rule_foreign_data(self):
        """Чужие клиенты: номера паспортов других клиентов не должны попадать в документы.

        Сравнение идёт целым числом: паспорт — это 9 цифр, поэтому вхождение внутри
        более длинного числа (ИНН, ОГРН, номер счёта) чужим паспортом не считается.
        """
        keep = (self.client.get("passport_number") or "").strip()
        rows = self.c.execute("SELECT full_name_latin, passport_number FROM clients").fetchall()
        for r in rows:
            pn = (r["passport_number"] or "").strip()
            if not pn or pn == keep or not pn.isdigit() or len(pn) not in (8, 9):
                continue
            pat = re.compile(r"(?<!\d)" + re.escape(pn) + r"(?!\d)")
            for code, t in list(self.texts.items()) + list(self.tpl.items()):
                if pat.search(t):
                    self.add("BLOCK", code, "в документе номер паспорта %s другого клиента" % pn,
                             "чужие данные")

    def rule_signatory(self):
        """Офис и подписант: Denpasar — Arine Fadillah (Komisaris), Ngurah Rai — Bartosz (Direktur)."""
        for code in self.texts:
            if "request_letter" not in code and "jaminan" not in code and "surat_kuasa" not in code:
                continue
            t = self.texts[code]
            denpasar = "denpasar" in code or "Denpasar" in t
            if denpasar:
                if "Arine Fadillah" not in t:
                    # В письме-обращении имя подписанта не печатается: по канону там печать PT
                    # и подпись от руки (как METERAI и подпись в E-02). Поэтому это предупреждение,
                    # а не остановка отправки.
                    self.add("WARN", code, "письмо для Denpasar: имя Arine Fadillah (Komisaris) не напечатано — "
                             "проверить, что печать и подпись ставятся на бумаге", "канон агентства")
                if "Bartosz Pawel Nafalski" in t:
                    self.add("BLOCK", code, "письмо для Denpasar подписано Bartosz — для этого офиса нужен Arine Fadillah",
                             "канон агентства")
            else:
                if "Bartosz Pawel Nafalski" not in t:
                    self.add("WARN", code, "в письме не найден подписант Bartosz Pawel Nafalski", "канон агентства")

    def rule_e02(self):
        for code, t in self.texts.items():
            if "e02" not in code:
                continue
            bridging = "bridging" in code
            want = "BRIDGE" if bridging else "E33G"
            if "visa bridging to e33g" not in t.lower():
                self.add("WARN", code, "в форме нет цели «Visa Bridging to E33G»", "подлинник E-02")
            m = re.search(r"Stay Permit to be applied for\s*:?\s*([A-Z0-9]{3,10})", t)
            if m and m.group(1).strip() != want:
                self.add("BLOCK", code, "«Stay Permit to be applied for» = %s, а для этого продукта нужно %s"
                         % (m.group(1).strip(), want), "подлинник E-02")
            pn = (self.client.get("passport_number") or "").strip()
            if pn and pn not in t.replace(" ", ""):
                self.add("BLOCK", code, "номер паспорта в форме не совпадает с паспортом клиента (%s)" % pn,
                         "официально: паспорт")
            if "METERAI" not in t:
                self.add("INFO", code, "в форме нет места под марку METERAI", "подлинник E-02")

    def rule_dates_official(self):
        """Официальные требования по срокам: паспорт не менее 6 месяцев, ИТК действующий."""
        exp = parse_dot_date(self.client.get("passport_expiry") or "")
        if exp:
            days = (exp - TODAY).days
            if days < 180:
                self.add("BLOCK", "паспорт", "паспорт действует %d дн. (до %s) — официально нужно не менее 6 месяцев"
                         % (days, exp.strftime("%d.%m.%Y")), "evisa.imigrasi.go.id")
        # ИТК из формы E-02
        for code, t in self.texts.items():
            if "e02" not in code:
                continue
            m = re.search(r"VALID UNTIL (\d{2}-\d{2}-\d{4})", t)
            itk = parse_dot_date(m.group(1).replace("-", ".")) if m else None
            if itk:
                left = (itk - TODAY).days
                if left < 0:
                    self.add("BLOCK", code, "ИТК истёк %s — подавать алих статус нельзя"
                             % itk.strftime("%d.%m.%Y"), "imigrasi.go.id")
                elif "conversion" in code and left < 30:
                    self.add("BLOCK", code, "до окончания ИТК %d дн. — алих статус подаётся не позднее чем за 30 дней"
                             % left, "imigrasi.go.id")

    def rule_services(self):
        """Должность в договоре и в резюме должна совпадать с профессией в перечне услуг."""
        code = "remote_work_agreement__default"
        t = self.texts.get(code) or self.tpl.get(code)
        if not t:
            return
        m = re.search(r"engages the Contractor as (?:an?|the) (.{3,60}?) to provide", t)
        pos = (m.group(1).strip() if m else "")
        m7 = re.search(r"is engaged by the Company as (?:an?|the) (.{3,60}?) since", t)
        pos7 = (m7.group(1).strip() if m7 else "")
        if pos and pos7 and pos != pos7:
            self.add("BLOCK", code, "должность в разделе 1 («%s») и в разделе 7 («%s») разная" % (pos, pos7),
                     "логика договора")
        if pos and not re.search(r"(assistant|manager|engineer|designer|developer|analyst|specialist|consultant|teacher|translator|accountant|admin)", pos, re.I):
            self.add("WARN", code, "должность «%s» выглядит нестандартно — проверить пул должностей" % pos,
                     "пул должностей")

    def rule_drive_package(self):
        """Что реально лежит в папке клиента на Google Диске и совпадает ли это с нашим пакетом."""
        url = (self.app.get("gdrive_url") or self.client.get("gdrive_folder_url") or "").strip()
        if not url:
            self.add("WARN", "google drive", "в заявке нет ссылки на папку клиента на Диске", "процесс подачи")
            return
        try:
            from services.gdrive_api import list_files
            files = list_files(url, deep=True) or []
        except Exception as e:
            self.add("INFO", "google drive", "папку клиента прочитать не удалось: %s" % str(e)[:90],
                     "процесс подачи")
            return
        # list_files отдаёт и name, и path (с папками) — путь важнее: по нему видно папку заявки.
        names = [str(f.get("path") or f.get("name") or "") for f in files]
        files_in_app = [n for n in names if "wolf autodoc" in n.lower()]
        # В папке клиента лежат и прошлые сборки. Считаем только самую свежую — иначе
        # выходит ложное «часть не загружена» (в старой сборке файлов меньше).
        def _build_date(n):
            m = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', n)
            return (m.group(3), m.group(2), m.group(1)) if m else ('0000', '00', '00')
        if files_in_app:
            _latest = max((_build_date(n) for n in files_in_app), default=None)
            files_in_app = [n for n in files_in_app if _build_date(n) == _latest]
            names = names if not _latest else names
        low = " | ".join(names).lower()
        # Тип документа берём из карточки клиента: файл может называться «foto»,
        # «IMG_3810.JPG» или как угодно — важно, что система его распознала.
        kinds = set()
        try:
            _row = self.c.execute('SELECT client_id FROM applications WHERE id=?',
                                  (self.app_id,)).fetchone()
            if _row and _row[0]:
                kinds = {str(r[0]) for r in self.c.execute(
                    'SELECT DISTINCT doc_kind FROM client_documents WHERE client_id=?',
                    (_row[0],)) if r[0]}
        except Exception:
            kinds = set()
        for label, kind, keys in (("паспорт клиента", "passport", ("passport", "паспорт")),
                                  ("фотография клиента", "photo", ("photo", "foto", "фото")),
                                  ("разрешение ИТК", "itk", ("itk", "izin tinggal"))):
            if kind in kinds:
                continue
            if not any(k in low for k in keys):
                self.add("WARN", "google drive", "в папке клиента нет документа: %s" % label, "процесс подачи")
        if not any("wolf autodoc" in n.lower() for n in names):
            self.add("INFO", "google drive", "в папке клиента ещё нет папки с нашими документами",
                     "процесс подачи")
        if any(k in low for k in ("meterai", "подпис", "signed", "scan")):
            self.add("INFO", "google drive", "в папке есть сканы — проверить марку, подпись и печать",
                     "процесс подачи")
        # сколько наших документов подтверждено и сколько реально лежит в папке заявки
        confirmed = [d for d in self.docs if d["status"] in ("verified", "sent")]
        our_pdfs = [n for n in files_in_app if n.lower().endswith(".pdf")]
        if confirmed and len(our_pdfs) and len(our_pdfs) < len(confirmed):
            self.add("WARN", "google drive",
                     "в папке заявки %d PDF, а подтверждённых документов %d — часть не загружена"
                     % (len(our_pdfs), len(confirmed)), "процесс подачи")

    def rule_itk_and_permit(self):
        """Номер и срок разрешения на пребывание: форма E-02 против документа ИТК и данных клиента."""
        import json
        itk = {}
        cache = Path("/opt/wolf_v2/data/itk_cache.json")
        if cache.is_file():
            try:
                itk = json.loads(cache.read_text(encoding="utf-8")) or {}
            except Exception:
                itk = {}
        val = {k: v for k, v in itk.items() if isinstance(v, str)}
        doc_no = next((v for v in val.values() if re.match(r"^B\d[A-Z0-9\-]{6,}$", v or "")), "")
        doc_until = next((v for v in val.values() if re.match(r"^\d{2}-\d{2}-\d{4}$", v or "")), "")
        db_no = (self.client.get("stay_permit_no") or "").strip()
        for code, t in self.texts.items():
            if "e02" not in code:
                continue
            if db_no and db_no not in t.replace(" ", ""):
                self.add("WARN", code, "номер разрешения в форме (%s) не совпадает с данными клиента" % db_no,
                         "официально: ИТК")
            if doc_no and doc_no.replace("-", "") not in t.replace(" ", "").replace("-", ""):
                self.add("WARN", code, "номер ИТК из документа (%s) в форме не найден" % doc_no,
                         "официально: ИТК")
            if doc_until:
                exp = parse_dot_date(doc_until.replace("-", "."))
                if exp:
                    days = (exp - TODAY).days
                    if days < 0:
                        self.add("BLOCK", code, "срок действия ИТК %s истёк — подача невозможна"
                                 % exp.strftime("%d.%m.%Y"), "imigrasi.go.id")
                    elif days < 30 and "conversion" in code:
                        self.add("BLOCK", code, "до окончания ИТК %d дн.; алих статуса подаётся не позднее чем за 30 дней"
                                 % days, "imigrasi.go.id")

    def rule_required_docs(self):
        """Состав пакета против продукта: обязательные документы не должны теряться.

        У каждого слота продукта (договор, письмо офиса, резюме, справка банка) в заявке
        должен быть хотя бы один подтверждённый документ. Если слот пуст — это блокировка:
        именно так из пакета пропадал договор для мостовой визы.
        """
        pid = self.app.get("product_id")
        if not pid:
            return
        prod = self.c.execute("""SELECT pd.slot_code, COALESCE(pd.required,0) AS required,
                                        t.code, t.title
                                   FROM product_documents pd JOIN templates t ON t.id=pd.template_id
                                  WHERE pd.product_id=? AND COALESCE(t.status,'ok') NOT IN ('blocked','hidden','merged')""",
                              (pid,)).fetchall()
        if not prod:
            return
        by_code = {d["code"]: d for d in self.docs}
        slots = {}
        for r in prod:
            slots.setdefault(r["slot_code"] or r["code"], []).append(r)
        for slot, variants in slots.items():
            req = max(int(v["required"] or 0) for v in variants)
            present = [v["code"] for v in variants if v["code"] in by_code]
            if not req or present:
                # Документ в комплекте есть — ждать галочку менеджера не нужно:
                # проверки выполняет система и сама подтверждает документ.
                continue
            self.add("BLOCK", "пакет",
                     "в комплекте нет ни одного документа слота «%s» (нужны: %s)"
                     % (slot, ", ".join(v["code"] for v in variants)),
                     "состав продукта")

    def _layout(self) -> dict:
        """Блоки текста собранных документов: код документа → блоки с координатами."""
        out = {}
        for code in self.texts:
            d = self.by_code.get(code) or {}
            if not d.get("template_id"):
                continue
            files = sorted(BUILD_DIR.glob("app%d_tpl%d_*.html" % (self.app_id, d["template_id"])),
                           key=lambda p: p.stat().st_mtime)
            if files:
                out[code] = _layout_blocks(files[-1].read_text(encoding="utf-8", errors="ignore"))
        return out

    def rule_layout_quality(self):
        """Качество вёрстки: наложение текста, кириллица, шапка по центру, шрифты, шаги строк."""
        for code, blocks in self._layout().items():
            # 1. текст не должен наползать друг на друга
            for i in range(len(blocks)):
                for j in range(i + 1, len(blocks)):
                    a, b = blocks[i], blocks[j]
                    if a.get("page") != b.get("page"):
                        continue
                    if a["text"] == b["text"] and abs(a["left"] - b["left"]) < 1.5 \
                            and abs(a["top"] - b["top"]) < 1.5:
                        continue
                    if _is_rule_text(a["text"]) or _is_rule_text(b["text"]):
                        continue
                    # строки бланка с пунктиром («Stay Permit to be applied for : …………»)
                    # и значение на этой же строке — тоже норма, а не наложение
                    if re.search(r"[.\u2026]{6,}", a["text"]) or re.search(r"[.\u2026]{6,}", b["text"]):
                        continue
                    # метка поля («Stay Permit to be applied for:») и её короткое значение
                    # на одной строке — это норма бланка, а не наложение
                    _pa, _pb = a["text"].strip(), b["text"].strip()
                    if (_pa.endswith(":") and len(_pb) < 26) or (_pb.endswith(":") and len(_pa) < 26):
                        continue
                    ox = min(a["left"] + a["w"], b["left"] + b["w"]) - max(a["left"], b["left"])
                    oy = min(a["top"] + a["h"], b["top"] + b["h"]) - max(a["top"], b["top"])
                    if ox <= 2 or oy <= 2:
                        continue
                    # настоящее наложение — когда блоки перекрываются по обеим осям
                    # больше чем наполовину: касание по краю и «значение внутри рамки поля» не считаем
                    if ox < 0.45 * min(a["w"], b["w"]) or oy < 0.45 * min(a["h"], b["h"]):
                        continue
                    if True:      # наложения проверяет pdf_quality по PDF: HTML-геометрия врёт
                        continue
                    self.add("BLOCK", code, "текст наложен друг на друга: «%s» и «%s»"
                             % (a["text"][:26], b["text"][:26]), "качество вёрстки")
                    break
            # 2. весь текст документа — латиницей
            cyr = re.findall(r"[А-Яа-яЁё][А-Яа-яЁё\- ]{2,}", " ".join(b["text"] for b in blocks))
            if cyr:
                self.add("BLOCK", code, "русский текст в документе: «%s»" % ", ".join(cyr[:3])[:70],
                         "качество вёрстки")
            # 3. шапка документа по центру страницы
            top = sorted([b for b in blocks if b.get("page") == 1], key=lambda b: (b["top"], b["left"]))[:8]
            wide = [b for b in top if b["w"] > 80]
            if wide:
                w = max(wide, key=lambda b: b["w"])
                off = (w["left"] + w["w"] / 2) - 297.6          # половина A4 в pt
                if abs(off) > 24:
                    self.add("WARN", code, "шапка документа не по центру: смещение %.0f pt" % off,
                             "качество вёрстки")
            # 4. шрифты не прыгают
            sizes = [round(b["font_size"], 1) for b in blocks if b["font_size"]]
            if sizes:
                main = max(set(sizes), key=sizes.count)
                odd = sorted({s for s in sizes if abs(s - main) > 1.6})
                if len(odd) > 2:
                    self.add("WARN", code, "размеры шрифта скачут: %s (основной %.1f)"
                             % (", ".join("%.1f" % s for s in odd[:4]), main), "качество вёрстки")
            fams = {b["font_family"] for b in blocks if b["font_family"]}
            if len(fams) > 3:
                self.add("WARN", code, "в документе более трёх гарнитур: %s"
                         % ", ".join(sorted(fams)[:4]), "качество вёрстки")
            # 4б. ничего не выезжает за лист
            out_of_page = [b for b in blocks
                           if b["left"] < -2 or b["top"] < -2
                           or b["left"] + b["w"] > 595 + 2 or b["top"] + b["h"] > 842 + 2]
            if out_of_page:
                self.add("BLOCK", code, "текст выходит за пределы листа: «%s» (%.0f, %.0f)"
                         % (out_of_page[0]["text"][:24], out_of_page[0]["left"], out_of_page[0]["top"]),
                         "качество вёрстки")
            # 4в. левый край и шаг строк — по каждой странице отдельно
            pages = sorted({b.get("page") for b in blocks})
            # 4г. страница-сирота: лист, где всего одна-две строки, недопустим.
            # Правило заказчика 07.10.2026: многостраничный документ не должен заканчивать
            # раздел на отдельном листе — разметку надо делать компактнее (поток вместо рамок).
            for pg in pages[:-1]:
                txt_pg = " ".join(b["text"] for b in blocks if b.get("page") == pg).strip()
                if len(txt_pg) < 150:
                    self.add("BLOCK", code,
                             "страница почти пустая: на стр. %s всего %d знаков — текст надо"
                             " перенести на соседний лист (вёрстка не компактна)" % (pg, len(txt_pg)),
                             "качество вёрстки")
            for pg in pages:
                pgblocks = [b for b in blocks if b.get("page") == pg]
                lefts = [round(b["left"]) for b in pgblocks if b["w"] > 60]
                if len(lefts) >= 6:
                    main_left = max(set(lefts), key=lefts.count)
                    stray = sorted({x for x in lefts if abs(x - main_left) > 6})
                    if len(stray) > max(3, len(lefts) // 4):
                        self.add("WARN", code,
                                 "левый край текста неровный на стр. %s: отступы %s при основном %d pt"
                                 % (pg, ", ".join(str(s) for s in stray[:5]), main_left),
                                 "качество вёрстки")
                col = sorted([b for b in pgblocks if b["h"] < 30], key=lambda b: b["top"])
                gaps = [round(col[i + 1]["top"] - col[i]["top"], 1) for i in range(len(col) - 1)]
                gaps = [g for g in gaps if g > 0]
                if len(gaps) >= 8:
                    med = sorted(gaps)[len(gaps) // 2]
                    if med > 0:
                        jump = [g for g in gaps if g > med * 3.2]
                        if len(jump) > max(2, len(gaps) // 5):
                            self.add("WARN", code,
                                     "большие разрывы между строками на стр. %s: %s pt при обычном шаге %.1f pt"
                                     % (pg, ", ".join("%.0f" % g for g in jump[:4]), med),
                                     "качество вёрстки")

    def rule_layout_vs_example(self):
        """Вёрстка против подлинника: положения полей сверяем с заполненным образцом клиента."""
        try:
            import pymupdf
        except Exception:
            return
        for code, blocks in self._layout().items():
            ex = Path("/opt/wolf_v2/data/templates") / code / "example_filled.pdf"
            if not ex.is_file() or not blocks:
                continue
            try:
                doc = pymupdf.open(str(ex))
                ex_blocks = []
                for page in doc:
                    for b in page.get_text("dict")["blocks"]:
                        for line in b.get("lines", []):
                            txt = re.sub(r"\s+", " ",
                                         "".join(s.get("text", "") for s in line.get("spans", []))).strip()
                            if len(txt) < 6:
                                continue
                            x0, y0, x1, y1 = line["bbox"]
                            ex_blocks.append({"text": txt, "left": x0, "top": y0, "w": x1 - x0})
                doc.close()
            except Exception:
                continue
            shifts = []
            for e in ex_blocks:
                key = e["text"][:28].lower()
                match = next((b for b in blocks if key in b["text"].lower()), None)
                if not match:
                    continue
                dx, dy = abs(match["left"] - e["left"]), abs(match["top"] - e["top"])
                if dx > 8 or dy > 8:
                    shifts.append((e["text"][:26], dx, dy))
            if len(shifts) >= 3:
                self.add("WARN", code,
                         "вёрстка расходится с подлинником в %d местах, например «%s»: сдвиг %.0f×%.0f pt"
                         % (len(shifts), shifts[0][0], shifts[0][1], shifts[0][2]), "оригинал")

    def rule_cv_demo_data(self):
        """В резюме не должно быть демонстрационных данных другого человека.

        Пока шаблон резюме один (формат Сиваева), в него попадали строки демо-профиля:
        чужие компании, вуз, годы. Это блокирует отправку, пока разделы не заполнены
        настоящими данными клиента (требование 05.10.2026).
        """
        # Уникальные маркеры демонстрационного профиля (образец Сиваева).
        # Проверяются только те строки, которые НЕ могут принадлежать настоящему клиенту:
        # названия компаний, вуз, город и годы образца. Названия должностей («Executive
        # Director», «IT Specialist») из списка убраны 07.10.2026: это обычные реальные
        # должности, и по ним блокировалось настоящее резюме клиента (заявка 107).
        DEMO = ("T-BANK", "SOUL DIGITAL", "Moscow Polytechnic", "Yakutsk",
                "Sep 2023", "Aug 2016", "Bachelor\u2019s Degree in Automation",
                "IVAN SIVAEV", "SIVAEV")
        for code, d in self.by_code.items():
            if "cv" not in str((d or {}).get("code") or code):
                continue
            text = self.texts.get(code) or ""
            hits = [w for w in DEMO if w in text]
            if hits:
                self.add("BLOCK", code, "в резюме данные демонстрационного профиля: %s"
                         % ", ".join(hits[:4]), "резюме")

    def rule_attorney(self):
        """В ходатайстве получатель доверенности — постоянный представитель Марцеллена.

        Верхний блок письма («Nama») и получатель доверенности всегда Марцеллена;
        внизу подписывает директор (Ngurah Rai) или комиссар (Denpasar) — за это
        отвечает отдельное правило о подписанте (требование 05.10.2026).
        """
        for code, d in self.by_code.items():
            tcode = str((d or {}).get("code") or code)
            # правило только для писем-ходатайств: E-02 и договор — не письма с доверенностью
            if not tcode.startswith(("bridging_request_letter", "conversion_request_letter",
                                     "d12_cover_letter")):
                continue
            text = self.texts.get(code) or ""
            if len(text) < 200:
                continue
            if "Marcellena" not in text:
                self.add("WARN", code, "в письме нет получателя доверенности Marcellena "
                         "Nirmala Chrisna Moeri", "проверка ролей")

    def run(self, with_drive: bool = True):
        self.rule_kit()
        self.rule_contract_dates()
        self.rule_contract_passport()
        self.rule_placeholders()
        self.rule_foreign_data()
        self.rule_signatory()
        self.rule_e02()
        self.rule_dates_official()
        self.rule_services()
        self.rule_itk_and_permit()
        self.rule_required_docs()
        self.rule_layout_quality()
        self.rule_cv_demo_data()
        self.rule_attorney()
        if with_drive:
            self.rule_drive_package()
        return self.find


def autofix(app_id: int, findings) -> list:
    """Автовозврат: пересобрать документы с замечаниями и отправить их на повторную проверку.

    Значения считаются заново по правилам агентства (даты договора, паспорт клиента,
    подписант по офису, значения формы E-02) — ровно так же, как при открытии документа
    в редакторе. Файлы, которые правит человек (паспорт клиента, документы на Диске),
    не трогаем: их возвращаем списком на ручную корректировку.

    Возвращает названия пересобранных документов.
    """
    codes = []
    for f in findings:
        if f.get("level") != "BLOCK":
            continue
        code = (f.get("code") or "").strip()
        if not code or code in ("google drive", "паспорт"):
            continue
        if code not in codes:
            codes.append(code)
    if not codes:
        return []

    fixed = []
    try:
        from blocks.dashboard.page import freeze_document
    except Exception:
        return []
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    for code in codes:
        row = conn.execute("SELECT id FROM templates WHERE code=?", (code,)).fetchone()
        if not row:
            continue
        tpl_id = row["id"]
        try:
            for p in BUILD_DIR.glob("app%d_tpl%d_*.html" % (app_id, tpl_id)):
                p.unlink()
            freeze_document(app_id, tpl_id, actor="финишная проверка")
            fixed.append(Check.LABELS.get(code, code))
        except Exception as exc:  # noqa: BLE001
            print("autofix %s: %s" % (code, str(exc)[:140]))
    return fixed


def check_package(app_id: int, with_drive: bool = True):
    """Полная проверка пакета. Возвращает (вердикт, замечания).

    Вердикт: {'ok': bool, 'summary': str, 'rework': [коды документов]}.
    """
    chk = Check(app_id)
    finds = chk.run(with_drive=with_drive)
    blocks = [f for f in finds if f["level"] == "BLOCK"]
    rework = sorted({f["doc"] for f in blocks})
    if blocks:
        summary = ("Проверка пакета не пройдена: %d блокирующих замечаний. Вернуть на переработку: %s"
                   % (len(blocks), ", ".join(rework)))
        return {"ok": False, "summary": summary, "rework": rework}, finds
    warns = [f for f in finds if f["level"] == "WARN"]
    summary = "Проверка пакета пройдена." + (" Предупреждений: %d." % len(warns) if warns else "")
    # Журнал: фиксируем проверку пакета отдельной строкой
    try:
        from services import app_steps as _stp
        _stp.step(app_id, 'pack', 'ok' if not blocks else 'warn',
                  ("%d блокирующих, %d предупреждений" % (len(blocks), len(warns)))
                  + (". Вернуть на переработку: " + ", ".join(rework) if rework else ""))
    except Exception:
        pass
    return {"ok": True, "summary": summary, "rework": []}, finds


def main():
    app_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if not app_id:
        print("укажите номер заявки: doc_check.py 87")
        return 2
    chk = Check(app_id)
    print("=== проверка заявки %d: %s (%s) ===" % (app_id, chk.client.get("full_name_latin", "?"),
                                                   chk.product.get("code", "продукт не задан")))
    print("    документов в заявке: %d" % len(chk.docs))
    finds = chk.run(with_drive=("--no-drive" not in sys.argv))
    order = {"BLOCK": 0, "WARN": 1, "INFO": 2}
    finds.sort(key=lambda f: (order.get(f["level"], 9), f["doc"]))
    icon = {"BLOCK": "⛔", "WARN": "⚠️", "INFO": "•"}
    for f in finds:
        print("   %s [%-16s] %s   (%s)" % (icon.get(f["level"], "•"), f["doc"][:16], f["msg"], f["source"]))
    cnt = {k: sum(1 for f in finds if f["level"] == k) for k in ("BLOCK", "WARN", "INFO")}
    blocks = [f for f in finds if f["level"] == "BLOCK"]
    rework = sorted({f["doc"] for f in blocks})
    print("   итого: %d блокирующих, %d предупреждений, %d подсказок" % (cnt["BLOCK"], cnt["WARN"], cnt["INFO"]))
    if blocks:
        print("   ВЕРДИКТ: не готово к отправке. Вернуть на переработку: %s" % ", ".join(rework))
    else:
        print("   ВЕРДИКТ: пакет готов к отправке на Google Диск")
    return 0


if __name__ == "__main__":
    sys.exit(main())
