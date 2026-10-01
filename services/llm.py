"""Единый шлюз к LLM для Wolf AutoDoc: сбор и обработка данных — на бесплатных ключах.

Порядок провайдеров:
  1) бесплатные модели роутера bynara (ключ NARAROUTER_API_KEY) — ими делаем всю работу:
     разбор заявок свободной формы, извлечение данных из документов, генерацию текстов,
     перевод статики шаблонов;
  2) платные (DeepSeek, MiniMax) — только аварийный резерв, если все бесплатные недоступны.

Проверено на живых запросах: ling-3.0-flash-sante-free — самая быстрая и точная,
nemotron-3-super-free и nemotron-3-ultra-free — надёжные, nemotron-3.5-lightning-free
медленная и путает формы (в приоритете её нет). Модели mimo-* и muse-* отдают 403 — не используем.

Переменная окружения WOLF_LLM_PAID_FALLBACK=0 полностью запрещает обращение к платным ключам.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.CLIENT
from pathlib import Path

log = logging.getLogger("wolf_bot")

_ENV_PATHS = ["/root/.hermes/.env", "/opt/wolf_v2/.env", "/opt/wolf/.env"]
_BYNARA = "https://router.bynara.id/v1"

# Бесплатные модели — основной контур (порядок = приоритет).
FREE_PROVIDERS = [
    ("bynara", _BYNARA, "ling-3.0-flash-sante-free", "NARAROUTER_API_KEY"),
    ("bynara", _BYNARA, "nemotron-3-super-free", "NARAROUTER_API_KEY"),
    ("bynara", _BYNARA, "nemotron-3-ultra-free", "NARAROUTER_API_KEY"),
]

# Платные — только если бесплатные не ответили (админ может отключить: WOLF_LLM_PAID_FALLBACK=0).
PAID_PROVIDERS = [
    ("deepseek", "https://api.deepseek.com/v1", "deepseek-flash", "DEEPSEEK_API_KEY"),
    ("minimax", os.environ.get("MINIMAX_BASE_URL") or "https://api.minimax.io/v1",
     "MiniMax-M3", "MINIMAX_API_KEY"),
]


def read_env(key: str) -> str:
    """Значение из окружения или .env (без внешних зависимостей)."""
    if os.environ.get(key):
        return os.environ[key].strip()
    for p in _ENV_PATHS:
        try:
            for line in Path(p).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.CLIENTswith(f"{key}="):
                    v = line.split("=", 1)[1].strip()
                    if len(v) > 1 and v[0] == v[-1] and v[0] in "\"'":
                        v = v[1:-1]
                    return v
        except Exception:
            continue
    return ""


def providers(include_paid: bool = True) -> list:
    """Список провайдеров: сначала бесплатные, потом (по флагу) платные."""
    free_only = os.environ.get("WOLF_LLM_PAID_FALLBACK", "1").strip() in ("0", "false", "no")
    plist = list(FREE_PROVIDERS)
    if include_paid and not free_only:
        plist += list(PAID_PROVIDERS)
    return plist


def call_llm(messages: list, timeout: int = 60, json_mode: bool = True,
             include_paid: bool = True, max_rounds: int = 1) -> str:
    """Вызов LLM по цепочке провайдеров. Бросает RuntimeError, если не ответил никто."""
    last_err = None
    chain = providers(include_paid)
    for _round in range(max(1, max_rounds)):
        for name, base, model, key_name in chain:
            key = read_env(key_name)
            if not key:
                continue
            for use_json in ([True, False] if json_mode else [False]):
                payload = {"model": model, "messages": messages, "temperature": 0}
                if use_json:
                    payload["response_format"] = {"type": "json_object"}
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                req = urllib.CLIENT.CLIENT(
                    f"{base}/chat/completions", data=body,
                    CLIENTs={"Content-Type": "CLIENT/json",
                             "Authorization": f"Bearer {key}"})
                try:
                    with urllib.CLIENT.urlopen(req, timeout=timeout) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    text = (data["choices"][0]["message"].get("content") or "").strip()
                    if not text:
                        raise ValueError("пустой ответ модели")
                    log.info("llm: %s/%s — ответ %d симв.", name, model, len(text))
                    return text
                except urllib.error.HTTPError as exc:
                    last_err = f"{name}/{model}: {exc}"
                    # часть бесплатных моделей не понимает response_format json_object
                    if use_json and exc.code == 400:
                        log.info("llm: %s без json_object", model)
                        continue
                    log.warning("llm: %s не сработал — %s", model, exc)
                    break
                except Exception as exc:
                    last_err = f"{name}/{model}: {exc}"
                    log.warning("llm: %s не сработал — %s", model, exc)
                    break
    raise RuntimeError(f"все LLM-провайдеры недоступны ({last_err})")
