#!/usr/bin/env python3
"""Probe app #122 for cron (v3, correct columns)."""
import os
import sys
import time

sys.path.insert(0, "/opt/wolf_v2")
from core import db as db_mod  # type: ignore


def rows(sql, params=()):
    return db_mod.q(sql, params)


def v(rs):
    if not rs:
        return "<empty>"
    return "\n".join("  ".join(str(x) for x in r.values()) for r in rs)


print("--- applications[id=122] ---")
print(v(rows("SELECT id, status, product_id, client_id, "
            "source, substr(created_at,1,19), substr(sent_at,1,19) "
            "FROM applications WHERE id=122")))

print("\n--- auto_runs #122 (DESC 10) ---")
print(v(rows(
    "SELECT id, stage, ok, sent, files, "
    "substr(note,1,90), finished_at "
    "FROM auto_runs WHERE application_id=122 "
    "ORDER BY id DESC LIMIT 10"
)))

print("\n--- app_steps #122 (DESC 8) ---")
print(v(rows(
    "SELECT id, step, status, substr(note,1,90), "
    "substr(created_at,1,19), actor "
    "FROM app_steps WHERE application_id=122 "
    "ORDER BY id DESC LIMIT 8"
)))

print("\n--- application_documents #122 (by template_id) ---")
print(v(rows(
    "SELECT id, template_id, status, "
    "substr(rendered_at,1,19), substr(pdf_path,1,40), error "
    "FROM application_documents WHERE application_id=122 "
    "ORDER BY template_id"
)))

print("\n--- auto_queue #122 (DESC 5) ---")
print(v(rows(
    "SELECT id, status, attempts, substr(last_error,1,80), "
    "substr(finished_at,1,19) FROM auto_queue WHERE application_id=122 "
    "ORDER BY id DESC LIMIT 5"
)))

print("\n--- logical_checks #122 (DESC 5) ---")
print(v(rows(
    "SELECT id, ok, blocks, substr(warns,1,50), substr(report,1,90), "
    "checked_at FROM logical_checks WHERE application_id=122 "
    "ORDER BY id DESC LIMIT 5"
)))

print("\n--- quality_checks #122 (DESC 5) ---")
print(v(rows(
    "SELECT id, code, ok, blocks, "
    "substr(reasons,1,90), substr(ts,1,19) "
    "FROM quality_checks WHERE app_id=122 "
    "ORDER BY id DESC LIMIT 5"
)))

print("\n--- events (any) DESC 15 ---")
print(v(rows(
    "SELECT id, entity, entity_id, action, "
    "substr(payload,1,90), actor, substr(created_at,1,19) "
    "FROM events ORDER BY id DESC LIMIT 15"
)))

print("\nNOW UTC:", db_mod.q1(
    "SELECT strftime('%Y-%m-%dT%H:%M:%SZ','now')", ()
))

out_dir = "/opt/wolf_v2/data/out/122"
ren_dir = "/opt/wolf_v2/data/renders/122"
print("\nout/122:", os.path.isdir(out_dir), "  renders/122:", os.path.isdir(ren_dir))
for d in (out_dir, ren_dir):
    if os.path.isdir(d):
        files = []
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            if os.path.isfile(p):
                files.append((f, time.strftime('%H:%M:%S', time.gmtime(os.path.getmtime(p))), os.path.getsize(p)))
        print(f"  {d}: {len(files)} files")
        for f in files:
            print(" ", f)
