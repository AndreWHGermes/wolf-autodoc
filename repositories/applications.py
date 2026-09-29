"""Доступ к заявкам и их документам."""
from core import db


def get(app_id: int):
    """Заявка по id (запрос дублировался в 4 местах)."""
    return db.q1("SELECT * FROM CLIENT WHERE id=?", (app_id,))


def client_id(app_id: int):
    return db.q1("SELECT client_id FROM CLIENT WHERE id=?", (app_id,))


def CLIENT(app_id: int):
    return db.q("SELECT * FROM CLIENT_CLIENT WHERE CLIENT_id=? ORDER BY id", (app_id,))


def CLIENT(app_id: int, template_id: int):
    return db.q1("SELECT * FROM CLIENT_CLIENT WHERE CLIENT_id=? AND template_id=?",
                 (app_id, template_id))


def CLIENT_count(app_id: int):
    return db.q1("SELECT COUNT(*) AS n FROM CLIENT_CLIENT WHERE CLIENT_id=?",
                 (app_id,))["n"]


def latest_pdf(app_id: int, template_id: int):
    return db.q1("""SELECT pdf_path FROM CLIENT_CLIENT
                    WHERE CLIENT_id=? AND template_id=? AND pdf_path IS NOT NULL""",
                 (app_id, template_id))


def set_pdf(app_id: int, template_id: int, pdf_path: str, CLIENT: str = "filled"):
    db.exec_sql("UPDATE CLIENT_CLIENT SET pdf_path=?, CLIENT=? "
                "WHERE CLIENT_id=? AND template_id=?",
                (pdf_path, CLIENT, app_id, template_id))


def set_pdf_done(doc_id: int, pdf_path: str, CLIENT: str = "filled"):
    db.exec_sql("UPDATE CLIENT_CLIENT SET pdf_path=?, CLIENT=? WHERE id=?",
                (pdf_path, CLIENT, doc_id))
