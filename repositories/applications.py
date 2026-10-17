"""Доступ к заявкам и их документам."""
from core import db


def get(app_id: int):
    """Заявка по id (запрос дублировался в 4 местах)."""
    return db.q1("SELECT * FROM applications WHERE id=?", (app_id,))


def client_id(app_id: int):
    return db.q1("SELECT client_id FROM applications WHERE id=?", (app_id,))


def documents(app_id: int):
    return db.q("SELECT * FROM application_documents WHERE application_id=? ORDER BY id", (app_id,))


def document(app_id: int, template_id: int):
    return db.q1("SELECT * FROM application_documents WHERE application_id=? AND template_id=?",
                 (app_id, template_id))


def documents_count(app_id: int):
    return db.q1("SELECT COUNT(*) AS n FROM application_documents WHERE application_id=?",
                 (app_id,))["n"]


def latest_pdf(app_id: int, template_id: int):
    return db.q1("""SELECT pdf_path FROM application_documents
                    WHERE application_id=? AND template_id=? AND pdf_path IS NOT NULL""",
                 (app_id, template_id))


def set_pdf(app_id: int, template_id: int, pdf_path: str, status: str = "filled"):
    db.exec_sql("UPDATE application_documents SET pdf_path=?, status=? "
                "WHERE application_id=? AND template_id=?",
                (pdf_path, status, app_id, template_id))


def set_pdf_done(doc_id: int, pdf_path: str, status: str = "filled"):
    db.exec_sql("UPDATE application_documents SET pdf_path=?, status=? WHERE id=?",
                (pdf_path, status, doc_id))
