
import sys
sys.path.insert(0, "/opt/wolf_v2")
pw = open("/root/.wolf_v2_admin.txt", encoding="utf-8").read().strip()
from app import app
c = app.test_client()
r = c.post("/login", data={"action": "password", "login": "admin", "password": pw}, follow_redirects=False)
print("POST /login ->", r.status_code, r.headers.get("Location"))
for url in ("/", "/templates/3", "/templates/3?ok=1"):
    p = c.get(url, follow_redirects=False)
    print("GET", url, "->", p.status_code, p.headers.get("Location"))
p = c.get("/templates/3", follow_redirects=True)
html = p.get_data(as_text=True)
print("с переходом:", p.status_code, len(html))
for needle in ("var-side", "vars-fold", "tpl-pdf-btn", "pv-title"):
    print("   ", needle, html.count(needle))
i_prev, i_panel, i_pdf = html.find('tb-label">Просмотр'), html.find('id="pv-title"'), html.find('id="tpl-pdf-open"')
print("   порядок (строка Просмотр < шапка окна < кнопка PDF):", i_prev, i_panel, i_pdf, i_prev < i_panel < i_pdf)
open("/tmp/t3_render.html", "w", encoding="utf-8").write(html)
