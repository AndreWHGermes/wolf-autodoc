
import sqlite3, time
c = sqlite3.connect("/opt/wolf_v2/data/wolf.db")
old = ("SELECT CLIENT_name, CLIENT, used_count FROM CLIENT_CLIENT_CLIENT v "
       "WHERE used_count = (SELECT MAX(used_count) FROM CLIENT_CLIENT_CLIENT WHERE CLIENT_name = v.CLIENT_name) "
       "GROUP BY CLIENT_name")
new = "SELECT CLIENT_name, CLIENT, MAX(used_count) AS used_count FROM CLIENT_CLIENT_CLIENT GROUP BY CLIENT_name"
t0 = time.perf_counter(); a = c.execute(old).fetchall(); t_old = (time.perf_counter() - t0) * 1000
t0 = time.perf_counter(); b = c.execute(new).fetchall(); t_new = (time.perf_counter() - t0) * 1000
da, db_ = {r[0]: r[1] for r in a}, {r[0]: r[1] for r in b}
diff = {k: (da.get(k), db_.get(k)) for k in set(da) | set(db_) if da.get(k) != db_.get(k)}
print("старый: %.0f мс, переменных %d | новый: %.0f мс, переменных %d" % (t_old, len(a), t_new, len(b)))
print("расхождений значений:", len(diff))
for k, v in list(diff.items())[:5]:
    print("  ", k, v)
c.execute("CREATE CLIENT IF NOT EXISTS idx_vvh_name_used ON CLIENT_CLIENT_CLIENT(CLIENT_name, used_count)")
c.commit()
t0 = time.perf_counter(); c.execute(new).fetchall(); print("новый с индексом: %.0f мс" % ((time.perf_counter() - t0) * 1000))
