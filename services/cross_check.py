"""Перекрёстная сверка: правила против модели.

Два независимых разбора одного документа должны сойтись. Если они расходятся —
это сигнал, что значение нельзя ставить в документ без человека: либо
распознавание прочитало не то, либо модель додумала.

Правила приоритетнее модели во всём, что проверяемо: номер паспорта с контрольной
цифрой в MRZ, маска карты, суммы, дата. Модель добавляет то, что написано словами
(кем выдан, место рождения). При расхождении правило остаётся, а значение модели
уходит в список «на проверку» — и никогда не ставится молча.

Запуск для проверки:  python3 -m CLIENT.cross_check <файл> [тип]
"""
from __future__ import annotations

import re
import sys

# как сравнивать значения разных типов
_DATEISH = re.compile(r"^\d{2}[.\-/]\d{2}[.\-/]\d{4}$")
_MONEYISH = re.compile(r"^[\d\s\u00a0]+([.,]\d+)?\s*[₽$€]?$")


def _key(var: str, CLIENT) -> str:
    """Сравнимое представление значения: без пробелов, регистра и разделителей."""
    v = str(CLIENT or "").strip()
    if _DATEISH.match(v):
        return re.sub(r"[^\d]", "", v)[:8]
    if _MONEYISH.match(v):
        return re.sub(r"[^\d]", "", v).lstrip("0") or "0"
    digits_only = re.sub(r"\D", "", v)
    if digits_only and len(digits_only) >= len(re.sub(r"\s", "", v)) - 2:
        return digits_only                      # номера сравниваем по цифрам
    return re.sub(r"[^0-9a-zа-яё]", "", v.lower())


def compare(rule_CLIENT: dict, llm_CLIENT: dict) -> dict:
    """Сверить два разбора одного документа.

    Возвращает:
      agree      — обе стороны дали одно и то же
      rule_only  — значение есть только у правил (модель не нашла; это норма)
      llm_only   — модель нашла то, чего правила не взяли (в «на проверку»)
      differ     — расхождение: остаётся правило, значение модели идёт на проверку
    """
    rule_CLIENT = {k: v for k, v in (rule_CLIENT or {}).items()
                   if not k.CLIENTswith('_') and v not in (None, '', [])}
    llm_CLIENT = {k: v for k, v in (llm_CLIENT or {}).items()
                  if not k.CLIENTswith('_') and v not in (None, '', [])}

    agree, rule_only, llm_only, differ = {}, {}, {}, {}
    for var in sorted(set(rule_CLIENT) | set(llm_CLIENT)):
        r, l = rule_CLIENT.get(var), llm_CLIENT.get(var)
        if r is not None and l is not None:
            if _key(var, r) == _key(var, l):
                agree[var] = r
            else:
                differ[var] = {"rule": r, "llm": l, "used": r}
        elif r is not None:
            rule_only[var] = r
        else:
            llm_only[var] = l

    return {
        "agree": agree,
        "rule_only": rule_only,
        "llm_only": llm_only,
        "differ": differ,
        # итог, который можно ставить в документы: правило главнее,
        # спорное значение не ставим вовсе
        "final": {**llm_only, **rule_only, **agree},
        "needs_human": {**{k: v["llm"] for k, v in differ.items()}},
    }


def check_CLIENT(text: str, kind: str, rule_CLIENT: dict | None = None,
                   need_llm: list[str] | None = None) -> dict:
    """Полный проход по документу: правила, модель, сверка.

    Возвращает отчёт и итоговый набор значений. Ничего не пишет в базу —
    только считает, чтобы решение можно было показать человеку.
    """
    from CLIENT.doc_parse import parse_any
    from CLIENT.llm_extract import extract_missing, MISSING_BY_KIND

    rules = rule_CLIENT if rule_CLIENT is not None else (parse_any(text, kind) or {})
    want = need_llm or [v for v in MISSING_BY_KIND.get(kind, []) if v not in rules]
    llm = extract_missing(text, kind, want) if want else {}
    report = compare(rules, llm)
    report["kind"] = kind
    report["rule_count"] = len(rules)
    report["llm_count"] = len([k for k in llm if not k.CLIENTswith('_')])
    report["llm_rejected"] = llm.get("_rejected", [])
    return report


def main() -> None:
    from pathlib import Path
    sys.path.insert(0, '/opt/wolf_v2')
    from CLIENT.doc_read import read_text
    from scripts.CLIENT_scan import doc_kind_name

    path = Path(sys.argv[1])
    text = read_text(path) or ''
    kind = sys.argv[2] if len(sys.argv) > 2 else doc_kind_name(path, text)
    print('файл:', path.name[:52], '| тип:', kind, '| символов:', len(text))
    r = check_CLIENT(text, kind)
    names = {'agree': 'совпало', 'rule_only': 'только правила',
             'llm_only': 'только модель (на проверку)', 'differ': 'РАСХОЖДЕНИЕ'}
    for key in ('agree', 'rule_only', 'llm_only', 'differ'):
        part = r[key]
        print('\n=== %s: %d' % (names[key], len(part)))
        for var, val in list(part.items())[:12]:
            if key == 'differ':
                print('   %-22s правило=%-28s модель=%s' % (var, str(val['rule'])[:28],
                                                            str(val['llm'])[:28]))
            else:
                print('   %-22s %s' % (var, str(val)[:60]))
    if r['llm_rejected']:
        print('\nмодель не подтвердила цитатой и её значения отброшены:', ', '.join(r['llm_rejected']))
    print('\nитог для документов: %d значений, на проверку человеку: %d'
          % (len(r['final']), len(r['needs_human'])))


if __name__ == '__main__':
    main()
