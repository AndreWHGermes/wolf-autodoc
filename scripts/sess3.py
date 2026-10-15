
import sys, re
sys.path.insert(0, "/opt/wolf_v2")
from app import app
c = app.test_client()
with c.session_transaction() as s:
    s["user_id"] = 1
    s["user_name"] = "admin"
    s["user_role"] = "admin"
    s["role"] = "admin"
with c.session_transaction() as s:
    print("сессия:", dict(s))
p = c.get("/templates/2", follow_redirects=True)
html = p.get_data(as_text=True)
print("страница:", p.status_code, len(html), "символов")
for needle in ("var-side", "var-tools", "vars-fold", "tpl-pdf-btn", "pv-title", "pl-vars"):
    print("   ", needle, "->", html.count(needle))
i_prev, i_panel, i_pdf = html.find('tb-label">Просмотр'), html.find('id="pv-title"'), html.find('id="tpl-pdf-open"')
print("   строка «Просмотр»:", i_prev, "| шапка окна:", i_panel, "| кнопка PDF:", i_pdf,
      "| PDF в шапке окна:", i_prev < i_panel < i_pdf)
open("/tmp/t3_render.html", "w", encoding="utf-8").write(html)
# cookie для браузера
r = c.get("/templates/2")
for h in r.headers.getlist("Set-Cookie"):
    m = re.search(r"(session=[^;]+)", h)
    if m:
        open("/tmp/sess.txt", "w").write(m.group(1).split("=", 1)[1])
        print("   cookie записан")
