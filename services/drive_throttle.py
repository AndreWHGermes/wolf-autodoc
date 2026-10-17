"""Ограничитель обращений к Google Диску: чтобы не долбить частыми запросами.

Google анонимно режет частые обращения к файлам («many accesses»), поэтому все
заходы на Диск идут через этот модуль: он держит паузу между запросами,
ограничивает число заходов в час, а при отказе увеличивает паузу (10 минут →
дальше 20, 1 час, 2 часа, 6 часов) вместо того, чтобы сразу долбить снова.

Правила простые: не чаще одного захода в MIN_GAP секунд и не больше
MAX_PER_HOUR заходов в час; отказ Google = длинная пауза, а не повтор.
"""
import json
import threading
import time
from datetime import datetime
from pathlib import Path

STATE = Path("/opt/wolf_v2/data/drive_throttle.json")

MIN_GAP = 12          # секунд между заходами на Диск
MAX_PER_HOUR = 12     # заходов в час
BACKOFF = [600, 1800, 3600, 7200, 21600]   # 10 мин → 20 мин → 1 ч → 2 ч → 6 ч

_lock = threading.Lock()


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _save(d: dict) -> None:
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass


def _hour_calls(d: dict) -> int:
    now = time.time()
    calls = [t for t in (d.get("calls") or []) if now - t < 3600]
    d["calls"] = calls
    return len(calls)


def _clock(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def can_call() -> tuple:
    """Можно ли сейчас идти на Диск. Возвращает (можно, причина ожидания)."""
    with _lock:
        d = _load()
        now = time.time()
        calls = _hour_calls(d)
        _save(d)
        nxt = float(d.get("next_at") or 0)
        if now < nxt:
            return False, f"Google ограничил обращения, следующая попытка в {_clock(nxt)}"
        if calls >= MAX_PER_HOUR:
            last = max(d.get("calls") or [now])
            return False, f"лимит {MAX_PER_HOUR} заходов в час исчерпан, продолжим после {_clock(last + 3600)}"
        return True, ""


def acquire(wait: bool = True, max_wait: int = 900) -> bool:
    """Пропускает заход на Диск: ждёт паузу между запросами. Для фоновых задач."""
    waited = 0
    while True:
        with _lock:
            d = _load()
            now = time.time()
            calls = [t for t in (d.get("calls") or []) if now - t < 3600]
            nxt = float(d.get("next_at") or 0)
            last = float(d.get("last") or 0)
            gap = MIN_GAP - (now - last)
            if now < nxt or len(calls) >= MAX_PER_HOUR or gap > 0:
                wait_for = max(nxt - now, gap, 5)
            else:
                d["last"] = now
                d["calls"] = calls + [now]
                _save(d)
                return True
        if not wait or waited >= max_wait:
            return False
        nap = min(wait_for, 30)
        time.sleep(nap)
        waited += nap


def report_ok() -> None:
    """Заход удался: сбрасываем счётчик отказов."""
    with _lock:
        d = _load()
        d["fails"] = 0
        d.pop("next_at", None)
        d["last_ok"] = time.time()
        _save(d)


def report_fail(reason: str = "") -> str:
    """Google не отдал данные: ставим длинную паузу, растущую с каждым отказом."""
    with _lock:
        d = _load()
        fails = int(d.get("fails") or 0)
        pause = BACKOFF[min(fails, len(BACKOFF) - 1)]
        d["fails"] = fails + 1
        d["next_at"] = time.time() + pause
        d["last_fail_note"] = reason[:200]
        _save(d)
        return f"пауза {int(pause / 60)} мин"


def state() -> dict:
    with _lock:
        d = _load()
        now = time.time()
        calls = _hour_calls(d)
        _save(d)
        nxt = float(d.get("next_at") or 0)
        ok = now >= nxt and calls < MAX_PER_HOUR
        return {
            "ok": ok,
            "wait_min": max(0, int((nxt - now + 59) // 60)),
            "fails": int(d.get("fails") or 0),
            "calls_last_hour": calls,
            "max_per_hour": MAX_PER_HOUR,
            "min_gap": MIN_GAP,
            "note": ("" if ok else (d.get("last_fail_note") or f"продолжим после {_clock(nxt)}")),
        }
