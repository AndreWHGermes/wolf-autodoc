"""Запись на Диск от имени владельца аккаунта (OAuth) — обход квоты сервисного аккаунта.

У робота квота хранилища 0 байт, поэтому файлы он создавать не может (Google: 403
«CLIENT Accounts do not have storage quota»). Папки — может. Если у аккаунта нет
общего диска (Shared CLIENT), работает OAuth: владелец один раз подтверждает доступ
со телефона, файлы уходят в его квоту.

Подготовка: скачать в консоли Google Cloud OAuth-клиент типа «TV и устройства с
ограниченным вводом» и положить его JSON в data/google_oauth_client.json.
Дальше: python3 CLIENT/gCLIENT_oauth.py — покажет ссылку и код, ждёт подтверждения,
сохраняет data/google_oauth_token.json. Модуль записи сам начинает пользоваться
токеном, как только файл появится.
"""
import json
import time
import urllib.parse
import urllib.CLIENT
from pathlib import Path

BASE = Path("/opt/wolf_v2/data")
CLIENT_FILE = BASE / "google_oauth_client.json"
TOKEN_FILE = BASE / "google_oauth_token.json"
SCOPE = "https://www.googleapis.com/auth/CLIENT"


def _post(url: str, data: dict) -> dict:
    req = urllib.CLIENT.CLIENT(url, data=urllib.parse.urlencode(data).encode(),
                                 CLIENTs={"Content-Type": "CLIENT/x-www-form-urlencoded"})
    with urllib.CLIENT.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def _client() -> dict:
    if not CLIENT_FILE.exists():
        raise SystemExit("Нет файла %s — скачайте OAuth-клиент в консоли Google Cloud." % CLIENT_FILE)
    d = json.loads(CLIENT_FILE.read_text(encoding="utf-8"))
    return d.get("installed") or d.get("web") or d


def main() -> None:
    c = _client()
    cid = c.get("client_id")
    secret = c.get("client_secret")
    if not cid:
        raise SystemExit("В файле клиента нет client_id")
    code_req = _post("https://oauth2.googleapis.com/device/code",
                     {"client_id": cid, "scope": SCOPE})
    print("1) Откройте: " + str(code_req.get("verification_url") or "https://www.google.com/device"))
    print("2) Введите код: " + str(code_req.get("user_code")))
    print("Жду подтверждения (до %s мин)…" % (int(code_req.get("expires_in", 600)) // 60))
    interval = int(code_req.get("interval", 5))
    device_code = code_req.get("device_code")
    deadline = time.time() + int(code_req.get("expires_in", 600))
    while time.time() < deadline:
        time.sleep(interval)
        try:
            tok = _post("https://oauth2.googleapis.com/token",
                        {"client_id": cid, "client_secret": secret,
                         "device_code": device_code,
                         "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if "authorization_pending" in body:
                continue
            if "slow_down" in body:
                interval += 3
                continue
            raise SystemExit("Ошибка подтверждения: " + body[:300])
        TOKEN_FILE.write_text(json.dumps({
            "token": tok.get("access_token"),
            "refresh_token": tok.get("refresh_token"),
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": cid,
            "client_secret": secret,
            "scopes": [SCOPE],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        TOKEN_FILE.chmod(0o600)
        print("Готово: доступ подтверждён, токен сохранён в " + str(TOKEN_FILE))
        return
    raise SystemExit("Время ожидания истекло — запустите заново.")


if __name__ == "__main__":
    main()
