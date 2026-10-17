#!/usr/bin/env python3
"""Мини-раннер тестов Wolf AutoDoc (без внешних зависимостей).

Запускает все функции test_* из файлов tests/test_*.py и печатает результат.
Когда в системе появится pytest, эти же тесты можно запускать им напрямую.
"""
from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))


def main() -> int:
    modules = sorted(p.stem for p in TESTS.glob('test_*.py'))
    total = passed = 0
    failures = []
    for name in modules:
        mod = importlib.import_module(name)
        for attr in sorted(dir(mod)):
            if not attr.startswith('test_'):
                continue
            fn = getattr(mod, attr)
            if not callable(fn):
                continue
            total += 1
            try:
                fn()
                passed += 1
                print(f'  ✅ {name}.{attr}')
            except Exception as e:  # noqa: BLE001
                failures.append((f'{name}.{attr}', e, traceback.format_exc()))
                print(f'  ❌ {name}.{attr}: {str(e)[:160]}')
    print(f'\nвсего тестов: {total} | прошло: {passed} | провалилось: {len(failures)}')
    for f, e, tb in failures:
        print(f'\n--- {f}\n{tb.splitlines()[-4] if tb else ""}')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
