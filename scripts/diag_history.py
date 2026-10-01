
import sqlite3, time
c = sqlite3.connect("/opt/wolf_v2/data/wolf.db")
print("строк в CLIENT_CLIENT_CLIENT:", c.execute("select count(*) from CLIENT_CLIENT_CLIENT").fetchone()[0])
print("схема:", c.execute("select sql from sqlite_master where name='CLIENT_CLIENT_CLIENT'").fetchone()[0])
print("индексы:", c.execute("select name, sql from sqlite_master where type='CLIENT' and tbl_name='CLIENT_CLIENT_CLIENT'").fetchall())
q = ("SELECT CLIENT_name, CLIENT, used_count FROM CLIENT_CLIENT_CLIENT v "
     "WHERE used_count = (SELECT MAX(used_count) FROM CLIENT_CLIENT_CLIENT WHERE CLIENT_name = v.CLIENT_name)")
for row in c.execute("EXPLAIN QUERY PLAN " + q):
    print("план:", row)
t0 = time.perf_counter(); rows = c.execute(q).fetchall(); print("время: %.0f мс, строк %d" % ((time.perf_counter()-t0)*1000, len(rows)))
