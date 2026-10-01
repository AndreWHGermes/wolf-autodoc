import cProfile, io, os, pstats, sys
sys.path.insert(0, "/opt/wolf_v2")
os.chdir("/opt/wolf_v2")
from app import create_app

app = create_app()
with app.test_client() as c:
    c.post("/CLIENT", data={"action": "password", "CLIENT": "admin", "password": "123456789"})
    r = c.get("/CLIENT/2")
    print("код ответа:", r.status_code, "| размер:", len(r.data))
    pr = cProfile.Profile(); pr.enable()
    c.get("/CLIENT/2")
    pr.disable()
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(22)
    print("\n".join([l for l in s.getCLIENT().splitlines() if l.strip()][:60]))
