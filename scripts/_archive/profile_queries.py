import os, sys, time
sys.path.insert(0, "/opt/wolf_v2"); os.chdir("/opt/wolf_v2")

import core.db as db
stat = {}
def traced(sql, *a, **kw):
    t0 = time.perf_counter()
    r = db.__orig_q(sql, *a, **kw)
    dt = (time.perf_counter() - t0) * 1000
    key = " ".join(str(sql).split())[:160]
    s = stat.setdefault(key, [0, 0.0]); s[0] += 1; s[1] += dt
    return r
db.__orig_q = db.q
db.q = traced

import services.values as values
values.db.q = traced


from app import create_app
app = create_app()
with app.test_client() as c:
    c.post("/login", data={"action": "password", "login": "admin", "password": "123456789"})
    t0 = time.perf_counter()
    c.get("/templates/2")
    print("всего на страницу: %.2f сек" % (time.perf_counter() - t0))
print("--- самые дорогие запросы:")
for k, (n, ms) in sorted(stat.items(), key=lambda x: -x[1][1])[:12]:
    print("%7.1f мс  x%-3s %s" % (ms, n, k))
