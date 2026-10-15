
import sqlite3, time
c = sqlite3.connect("/opt/wolf_v2/data/wolf.db")
print("строк в variable_value_history:", c.execute("select count(*) from variable_value_history").fetchone()[0])
print("схема:", c.execute("select sql from sqlite_master where name='variable_value_history'").fetchone()[0])
print("индексы:", c.execute("select name, sql from sqlite_master where type='index' and tbl_name='variable_value_history'").fetchall())
q = ("SELECT variable_name, value, used_count FROM variable_value_history v "
     "WHERE used_count = (SELECT MAX(used_count) FROM variable_value_history WHERE variable_name = v.variable_name)")
for row in c.execute("EXPLAIN QUERY PLAN " + q):
    print("план:", row)
t0 = time.perf_counter(); rows = c.execute(q).fetchall(); print("время: %.0f мс, строк %d" % ((time.perf_counter()-t0)*1000, len(rows)))
