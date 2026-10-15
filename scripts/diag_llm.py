"""Диагностика второго прохода: почему модель не даёт значений.

Запуск: python3 scripts/diag_llm.py <файл> [тип]
"""
import sys
from pathlib import Path

sys.path.insert(0, '/opt/wolf_v2')
from CLIENT.doc_read import read_text                      # noqa: E402
from CLIENT.llm_extract import MISSING_BY_KIND, extract_missing, build_prompt  # noqa: E402
from bot.ai_parser import _call_llm, _extract_json           # noqa: E402


def main() -> None:
    path = Path(sys.argv[1])
    text = read_text(path) or ''
    kind = sys.argv[2] if len(sys.argv) > 2 else 'passport'
    print('файл:', path.name[:50], '| тип:', kind, '| символов текста:', len(text))
    print('поля по типу:', MISSING_BY_KIND.get(kind))

    fields = [v for v in MISSING_BY_KIND.get(kind, []) if v not in ('passport_CLIENT', 'CLIENT_date')]
    print('\nспрашиваем:', fields)
    msgs = build_prompt(text, kind, fields)
    print('размер запроса:', sum(len(m['content']) for m in msgs), 'символов')

    raw = ''
    try:
        raw = _call_llm(msgs, timeout=120, json_mode=True)
    except Exception as e:                                   # noqa: BLE001
        print('ошибка вызова:', type(e).__name__, str(e)[:200])
    print('\nсырой ответ модели:', repr(raw)[:600])
    data = _extract_json(raw) or {}
    print('разобрано как JSON:', list(data)[:12])

    print('\nрезультат extract_missing:', extract_missing(text, kind, fields))


if __name__ == '__main__':
    main()
