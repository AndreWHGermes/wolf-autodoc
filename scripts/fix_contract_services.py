"""Перечень услуг в договоре — переменной вместо зашитого текста.

В шаблоне договора пункты услуг были захардкожены под прежнюю профессию, поэтому
при смене должности в заявке («Должность: артист-продюсер») в документе оставался
старый административно-дизайнерский текст. Теперь все пункты-строки «●» заменяются
одной переменной {{services_list}}, а стиль берётся от первого пункта.

Запуск: /usr/bin/python3 scripts/fix_contract_services.py [--apply]
"""
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

PATH = Path("/opt/wolf_v2/data/templates/remote_work_agreement__default/template.html")
VAR = "{{services_list}}"
apply = "--apply" in sys.argv

html = PATH.read_text(encoding="utf-8")

# все блоки .txt, текст которых начинается с маркера пункта
blocks = [(m.start(), m.end(), m.group(0)) for m in
          re.finditer(r'<div class="txt"[^>]*>.*?</div>', html, flags=re.S)]
def _is_service(plain: str) -> bool:
    """Пункт списка услуг. Пункт про сумму («● which is RUB … per month») не трогаем:
    он печатает вознаграждение и в перечень услуг профессии не входит."""
    if not re.match(r"\s*[\u25cf\u2022]", plain):
        return False
    low = plain.lower()
    return not ("rub" in low or "per month" in low or "per year" in low)


bullets = []
for start, end, frag in blocks:
    plain = re.sub(r"<[^>]+>", "", frag)
    if _is_service(plain):
        bullets.append((start, end, frag))

print("найдено пунктов-услуг:", len(bullets))
if not bullets:
    print("нечего менять")
    sys.exit(0)

first = bullets[0][2]
# стиль первого пункта сохраняем, но разрешаем перенос строк и задаём ширину
style = re.search(r'style="([^"]*)"', first).group(1)
style = re.sub(r"white-space:\s*pre", "white-space:normal", style)
if "width:" not in style:
    style += ";width:480pt" if not style.rstrip(";").endswith(";") else "width:480pt"
font = re.search(r"<span[^>]*>", first).group(0)

new_first = '<div class="txt" style="%s">%s%s</span></div>' % (style, font, VAR)

# заменяем с конца, чтобы координаты не съезжали
for start, end, frag in reversed(bullets[1:]):
    html = html[:start] + html[end:]
start, end, _ = bullets[0]
html = html[:start] + new_first + html[end:]

print("первый пункт → %s | удалено пунктов: %d" % (VAR, len(bullets) - 1))
if apply:
    shutil.copy2(PATH, PATH.with_name("template.html.bak_services_%s"
                                     % datetime.now().strftime("%Y%m%d_%H%M%S")))
    PATH.write_text(html, encoding="utf-8")
    print("шаблон перезаписан:", PATH)
else:
    print("режим просмотра — без --apply файл не менялся")
