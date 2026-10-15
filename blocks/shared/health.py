"""Эндпоинт живости сервиса.

Нужен, чтобы падение или зависание замечалось сразу: nginx, внешний
мониторинг или скрипт проверки могут дёрнуть /health и получить понятный
ответ. Без авторизации — отдаёт только факт работоспособности.
"""
import os
import sqlite3
import time


def register(app):
    started = time.time()

    @app.route("/health")
    def _wolf_health():  # pragma: no cover - простой ответ
        from flask import jsonify
        db_path = os.environ.get("WOLF_DB") or "/opt/wolf_v2/data/wolf.db"
        db_ok = False
        clients = apps = docs = 0
        try:
            c = sqlite3.connect(db_path)
            c.row_factory = sqlite3.Row
            clients = c.execute("SELECT COUNT(*) n FROM clients").fetchone()["n"]
            apps = c.execute("SELECT COUNT(*) n FROM applications").fetchone()["n"]
            docs = c.execute("SELECT COUNT(*) n FROM application_documents").fetchone()["n"]
            c.close()
            db_ok = True
        except Exception as e:
            return jsonify({"ok": False, "db": False, "error": str(e)[:200]}), 503

        log_path = "/opt/wolf_v2/logs/wolf.log"
        log_size = os.path.getsize(log_path) if os.path.exists(log_path) else 0
        return jsonify({
            "ok": True,
            "db": db_ok,
            "uptime_sec": round(time.time() - started, 1),
            "clients": clients,
            "applications": apps,
            "documents": docs,
            "log_bytes": log_size,
        })
