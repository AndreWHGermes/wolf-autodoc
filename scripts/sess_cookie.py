
import sys, re
sys.path.insert(0, "/opt/wolf_v2")
pw = open("/root/.wolf_v2_admin.txt", encoding="utf-8").read().strip()
from app import app
c = app.test_client()
r = c.post("/login", data={"action": "password", "login": "admin", "password": pw}, follow_redirects=False)
print("логин:", r.status_code)
page = c.get("/templates/3")
html = page.get_data(as_text=True)
print("страница /templates/3:", page.status_code, len(html), "символов")
for needle in ("var-side", "var-tools", "vars-fold", "tpl-pdf-btn", 'id="tpl-pdf-open"'):
    print("   ", needle, "->", html.count(needle))
# проверяем, что кнопка PDF стоит в шапке окна просмотра, а не в строке «Просмотр»
i_prev = html.find('tb-label">Просмотр')
i_pdf = html.find('id="tpl-pdf-open"')
i_panel = html.find('id="pv-title"')
print("   позиция строки «Просмотр»:", i_prev, "| pv-title:", i_panel, "| кнопка PDF:", i_pdf,
      "-> кнопка в шапке окна просмотра:", i_pdf > i_panel > i_prev)
# cookie сессии — для браузера
for h in getattr(page, "headers", []):
    pass
with c.session_transaction() as sess:
    print("   сессия активна:", "user_id" in sess or bool(sess))
ck = None
resp = c.post("/login", data={"action": "password", "login": "admin", "password": pw})
for h in resp.headers.getlist("Set-Cookie"):
    m = re.search(r"(session=[^;]+)", h)
    if m:
        ck = m.group(1)
if ck:
    open("/tmp/sess.txt", "w").write(ck.split("=", 1)[1])
    print("   cookie сохранён (session=…%d симв.)" % len(ck.split("=", 1)[1]))
