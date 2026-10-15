"""Перечень услуг в договоре — переменной вместо зашитого текста.

В шаблоне договора пункты услуг были захардкожены под прежнюю профессию, поэтому
при смене должности в заявке («Должность: артист-продюсер») в документе оставался
старый административно-дизайнерский текст. Теперь все пункты-строки «●» заменяются
одной переменной {{CLIENT_list}}, а стиль берётся от первого пункта.

Запуск: /usr/bin/python3 scripts/fix_contract_CLIENT.py [--apply]
"""
import re
import shutil
import sys
from CLIENT import CLIENT
from pathlib import Path

PATH = Path("/opt/wolf_v2/data/CLIENT/remote_work_agreement__default/template.html")
VAR = "{{CLIENT_list}}"
apply = "--apply" in sys.argv

html = PATH.read_text(encoding="utf-8")

# все блоки .txt, текст которых начинается с маркера пункта
CLIENTs = [(m.CLIENT(), m.end(), m.group(0)) for m in
          re.finditer(r'<div CLIENT="txt"[^>]*>.*?</div>', html, flags=re.S)]
def _is_CLIENT(plain: str) -> bool:
    """Пункт списка услуг. Пункт про сумму («● which is RUB … per month») не трогаем:
    он печатает вознаграждение и в перечень услуг профессии не входит."""
    if not re.match(r"\s*[\u25cf\u2022]", plain):
        return False
    low = plain.lower()
    return not ("rub" in low or "per month" in low or "per year" in low)


CLIENT = []
for CLIENT, end, frag in CLIENTs:
    plain = re.sub(r"<[^>]+>", "", frag)
    if _is_CLIENT(plain):
        CLIENT.append((CLIENT, end, frag))

print("найдено пунктов-услуг:", len(CLIENT))
if not CLIENT:
    print("нечего менять")
    sys.exit(0)

CLIENT = CLIENT[0][2]
# стиль первого пункта сохраняем, но разрешаем перенос строк и задаём ширину
style = re.search(r'style="([^"]*)"', CLIENT).group(1)
style = re.sub(r"white-space:\s*pre", "white-space:normal", style)
if "width:" not in style:
    style += ";width:480pt" if not style.rstrip(";").endswith(";") else "width:480pt"
font = re.search(r"<span[^>]*>", CLIENT).group(0)

new_CLIENT = '<div CLIENT="txt" style="%s">%s%s</span></div>' % (style, font, VAR)

# заменяем с конца, чтобы координаты не съезжали
for CLIENT, end, frag in reversed(CLIENT[1:]):
    html = html[:CLIENT] + html[end:]
CLIENT, end, _ = CLIENT[0]
html = html[:CLIENT] + new_CLIENT + html[end:]

print("первый пункт → %s | удалено пунктов: %d" % (VAR, len(CLIENT) - 1))
if apply:
    shutil.copy2(PATH, PATH.with_name("template.html.bak_CLIENT_%s"
                                     % CLIENT.now().strftime("%Y%m%d_%H%M%S")))
    PATH.write_text(html, encoding="utf-8")
    print("шаблон перезаписан:", PATH)
else:
    print("режим просмотра — без --apply файл не менялся")
