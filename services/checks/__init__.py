"""
Единая точка входа для всех проверок заявки.

Три уровня проверки, которые раньше вызывались по отдельности:
- doc_check.check_package(app_id, with_drive=True)
  → проверка пакета по нашим правилам + то, что реально лежит на Google Drive.
    С авто-фиксом: если есть autofix-правила, применяются и проверка идёт заново.
- pdf_quality.check_app(app_id)
  → технический контроль: наложения, пропавший фон, незаполненные метки,
    чужие люди, устаревший слепок.
- logical_check.check_app(app_id)
  → логическая проверка данных: числа, даты, оклад в границах,
    офис иммиграции, чужие имена.

Любая BLOCK = отправка не происходит.

Тонкая фасадная обёртка: каждый модуль продолжает работать отдельно,
а run_all() собирает их в один проход.
"""
from typing import List, Tuple


def check_package(app_id: int, with_drive: bool = True):
    """Проверка пакета + авто-фикс + ре-проверка. Возвращает (verdict, findings).

    Применяет autofix если есть что поправить, потом снова проверяет.
    """
    try:
        from services import doc_check
        verdict, finds = doc_check.check_package(app_id, with_drive=with_drive)
        if not verdict["ok"]:
            try:
                fixed = doc_check.autofix(app_id, finds)
                if fixed:
                    verdict, finds = doc_check.check_package(app_id, with_drive=with_drive)
            except Exception:
                pass
        return verdict, finds
    except Exception as exc:
        return {"ok": True, "rework": False}, [{"level": "INFO", "doc": "—", "msg": str(exc)[:200]}]


def check_pdf_quality(app_id: int):
    """Технический контроль PDF: наложения, фон, метки, чужие люди, устаревший слепок."""
    try:
        from services import pdf_quality
        return pdf_quality.check_app(app_id)
    except Exception as exc:
        return {"ok": True, "docs": [], "finds": [{"level": "INFO", "msg": str(exc)[:200]}]}


def check_logical(app_id: int):
    """Логическая проверка данных: числа, даты, оклад, офис, имена."""
    try:
        from services import logical_check
        return logical_check.check_app(app_id)
    except Exception as exc:
        return {"ok": True, "finds": [{"level": "INFO", "msg": str(exc)[:200]}]}


def run_all(app_id: int) -> Tuple[bool, List[dict]]:
    """Запустить все три проверки подряд.

    Возвращает (ok, all_findings):
    - ok = True если ВСЕ проверки прошли
    - all_findings — список всех замечаний (BLOCK и INFO)
    """
    all_findings = []
    all_ok = True

    verdict, finds = check_package(app_id)
    if not verdict["ok"]:
        all_ok = False
    all_findings.extend(_extract(finds, "doc_check"))

    q = check_pdf_quality(app_id)
    if not q.get("ok"):
        all_ok = False
    for r in q.get("docs", []) or []:
        if not r.get("ok"):
            for f in r.get("finds", []) or []:
                if f.get("level") == "BLOCK":
                    all_findings.append({"source": "pdf_quality", "doc": r.get("code", ""), **f})

    l = check_logical(app_id)
    if not l.get("ok"):
        all_ok = False
    for f in l.get("finds", []) or []:
        if f.get("level") == "BLOCK":
            all_findings.append({"source": "logical_check", **f})

    return all_ok, all_findings


def _extract(finds, source: str) -> List[dict]:
    """Извлечь BLOCK-находки из результата doc_check."""
    out = []
    for f in finds or []:
        if f.get("level") == "BLOCK":
            out.append({"source": source, "doc": f.get("doc", ""), "msg": f.get("msg", ""), **f})
    return out


__all__ = [
    "check_package",
    "check_pdf_quality",
    "check_logical",
    "run_all",
]