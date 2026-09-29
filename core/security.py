"""Ядро: пароли."""
from __future__ import annotations

import hashlib
import hmac
import os

ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                     bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:                                   # noqa: BLE001
        return False


def password_problems(password: str) -> list:
    """Требования к паролю администратора: возвращает список замечаний."""
    problems = []
    if len(password or "") < 8:
        problems.append("минимум 8 символов")
    if not any(c.isalpha() for c in password or ""):
        problems.append("нужны буквы")
    if not any(c.isdigit() for c in password or ""):
        problems.append("нужны цифры")
    if (password or "").strip().lower() in {"123", "1234", "12345", "admin", "password", "qwerty"}:
        problems.append("слишком простой пароль")
    return problems
