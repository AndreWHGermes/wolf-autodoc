"""Каналы LLM для Wolf AutoDoc: единая точка входа с приоритетами.

Андрей 17.10.2026:
- 'в настройках, где telegram-бот, разделить на две части: слева telegram,
 справа подключенная llm модель через тебя. Показывать визуально статус.
 Автоподключение: при сбое провайдеров система зовёт BiMax (этого агента)
 для разруливания ступоров.'

Цепочка вызова (по убыванию приоритета):
  1. Бесплатные: nararouter/nemotron-3.5-lightning-free (и др. free)
  2. Платные:    deepseek-andreyl → deepseek → minimax-M3
  3. BiMax:      delegate_task (если все провайдеры упали)
  4. Fallback:   ошибка, вызывающий код решает что делать

Каждый вызов фиксируется в services.app_steps — чтобы админ видел,
какой канал реально отработал (free/paid/agent).

Использование:
    from services.llm_channels import call
    text = call("промт", app_id=124, purpose="смысловая проверка")
"""
from __future__ import annotations

import os
import time
from typing import Optional

# Канал 1: бесплатные модели
FREE_LABELS = ("nararouter/nemotron-3.5-lightning-free", "nararouter/nemotron-3-ultra-free")
# Канал 2: платные провайдеры
PAID_LABELS = ("deepseek-andreyl", "deepseek-chat", "minimax/MiniMax-M3")
# Канал 3: BiMax (этот агент) — fallback если внешние провайдеры упали


def _log_step(app_id: Optional[int], channel: str, model: str, status: str, note: str) -> None:
    """Лог в app_steps: какая модель подключилась, для чего, с каким результатом."""
    if not app_id:
        return
    try:
        from services import app_steps as _stp
        _stp.step(app_id, 'llm_channel', status,
                  f"[{channel}] {model}: {note[:160]}")
    except Exception:
        pass


def call(prompt: str, app_id: Optional[int] = None,
         purpose: str = "", timeout: int = 60,
         json_mode: bool = False, max_tokens: int = 2000) -> dict:
    """Единая точка вызова LLM с каскадом каналов.

    Возвращает:
        {
            'text': '...',           # ответ модели (или '')
            'channel': 'free'|'paid'|'agent'|'none',
            'model': 'nararouter/nemotron-3.5-lightning-free',
            'ms': 1234,
            'ok': True|False,
            'note': '...',           # детали ошибки
        }

    Логика:
        1) пробуем бесплатные (FREE_LABELS) через services.llm.call_llm
        2) если не вышло — платные (PAID_LABELS)
        3) если и платные упали — BiMax через delegate_task
        4) BiMax недоступен → ok=False, текст ошибки в 'note'
    """
    started = time.time()

    # Канал 1: бесплатные
    try:
        from services.llm import call_llm as _llm
        t0 = time.time()
        text = _llm(prompt, timeout=min(timeout, 25), json_mode=json_mode,
                    max_tokens=max_tokens, only_free=True) or ""
        ms = int((time.time() - t0) * 1000)
        if text and len(text.strip()) > 0:
            _log_step(app_id, 'free', FREE_LABELS[0], 'ok',
                      f'{purpose}: ответ за {ms} мс, {len(text)} символов' if purpose else f'ответ за {ms} мс')
            return {'text': text, 'channel': 'free', 'model': FREE_LABELS[0],
                    'ms': ms, 'ok': True, 'note': ''}
    except Exception as exc:                           # noqa: BLE001
        free_err = str(exc)[:120]
    else:
        free_err = 'пустой ответ'

    # Канал 2: платные
    try:
        from services.llm import call_llm as _llm
        t0 = time.time()
        text = _llm(prompt, timeout=min(timeout, 30), json_mode=json_mode,
                    max_tokens=max_tokens, only_paid=True) or ""
        ms = int((time.time() - t0) * 1000)
        if text and len(text.strip()) > 0:
            _log_step(app_id, 'paid', PAID_LABELS[0], 'ok',
                      f'{purpose}: ответ за {ms} мс' if purpose else f'ответ за {ms} мс')
            return {'text': text, 'channel': 'paid', 'model': PAID_LABELS[0],
                    'ms': ms, 'ok': True, 'note': ''}
    except Exception as exc:                           # noqa: BLE001
        paid_err = str(exc)[:120]
    else:
        paid_err = 'пустой ответ'

    # Канал 3: BiMax (этот агент через delegate_task)
    try:
        from services.llm import call_agent as _agent
        t0 = time.time()
        text = _agent(prompt, timeout=min(timeout, 60)) or ""
        ms = int((time.time() - t0) * 1000)
        if text and len(text.strip()) > 0:
            _log_step(app_id, 'agent', 'BiMax (Hermes)', 'ok',
                      f'{purpose}: ответ за {ms} мс' if purpose else f'ответ за {ms} мс')
            return {'text': text, 'channel': 'agent', 'model': 'BiMax (Hermes)',
                    'ms': ms, 'ok': True, 'note': ''}
        agent_err = 'пустой ответ'
    except Exception as exc:                           # noqa: BLE001
        agent_err = str(exc)[:120]

    total_ms = int((time.time() - started) * 1000)
    note = (f'все каналы упали: free={free_err}; paid={paid_err}; '
            f'agent={agent_err}')
    _log_step(app_id, 'all', '—', 'fail', note)
    return {'text': '', 'channel': 'none', 'model': '—', 'ms': total_ms,
            'ok': False, 'note': note}
