"""Сверка HTML-шаблона с оригинальным примером: сходство вёрстки и текста.

Для каждого действующего документа берём оригинальный заполненный пример
(data/templates/<code>/example_filled.pdf) и наш HTML-шаблон, приводим оба к «скелету»
(текст без значений переменных, нормализованные пробелы) и считаем сходство.

Расхождение означает: в шаблоне другой текст/вёрстка, чем в оригинале — такой шаблон
нужно пересобрать по оригиналу (скрипты rebuild_letter.py / rebuild_bank_statement.py).

Выход: docs/TEMPLATES_VS_ORIGINALS.md и data/guide/tpl_match.json
"""
import json
import re
import sqlite3
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path('/opt/wolf_v2')
DB = ROOT / 'data' / 'wolf.db'
TPL = ROOT / 'data' / 'templates'
OUT_MD = ROOT / 'docs' / 'TEMPLATES_VS_ORIGINALS.md'
OUT_JSON = ROOT / 'data' / 'guide' / 'tpl_match.json'
VAR_RE = re.compile(r'\{\{\s*[a-zA-Z0-9_]+\s*\}\}')
TAG_RE = re.compile(r'<[^>]+>')
WS_RE = re.compile(r'\s+')


def norm(text: str) -> str:
    t = text.replace('\u00a0', ' ')
    t = WS_RE.sub(' ', t)
    return t.strip().lower()


def html_skeleton(path: Path) -> str:
    html = path.read_text(encoding='utf-8', errors='ignore')
    body = html.split('<style', 1)[0] + html.split('</style>', 1)[-1] if '<style' in html else html
    body = re.sub(r'<script.*?</script>', ' ', body, flags=re.S | re.I)
    body = re.sub(r'<style.*?</style>', ' ', body, flags=re.S | re.I)
    body = VAR_RE.sub(' ', body)          # значения переменных в сверке не участвуют
    body = TAG_RE.sub(' ', body)
    return norm(body)


def pdf_text(path: Path) -> str:
    try:
        import pymupdf
    except Exception:  # noqa: BLE001
        return ''
    try:
        doc = pymupdf.open(str(path))
    except Exception:  # noqa: BLE001
        return ''
    out = ' '.join(p.get_text() for p in doc)
    return norm(out)


def main() -> int:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    rows = con.execute("""SELECT code, title, status, doc_index FROM templates
                          WHERE COALESCE(status,'ok') NOT IN ('merged','hidden')
                          ORDER BY COALESCE(doc_index,999), code""").fetchall()
    result = {}
    md = ['# Сверка HTML-шаблонов с оригинальными примерами', '',
          'Сходство считается по тексту документа без значений переменных (они подставляются при сборке).', '']
    bad = []
    for r in rows:
        code = r['code']
        d = TPL / code
        html_p = d / 'template.html'
        orig_p = d / 'example_filled.pdf'
        if not html_p.is_file():
            md.append('- `%s` — **нет HTML-шаблона**' % code)
            bad.append((code, 'нет HTML', 0.0))
            continue
        skel = html_skeleton(html_p)
        if not orig_p.is_file():
            md.append('- `%s` — HTML есть, оригинального примера нет (нужно подобрать)' % code)
            result[code] = {'similarity': None, 'html_len': len(skel), 'note': 'нет оригинала'}
            bad.append((code, 'нет оригинала', 0.0))
            continue
        orig = pdf_text(orig_p)
        ratio = SequenceMatcher(None, skel, orig).ratio() if skel and orig else 0.0
        # дополнительно: сколько слов шаблона встречается в оригинале (устойчивее к порядку)
        sw, ow = set(skel.split()), set(orig.split())
        cover = len(sw & ow) / max(len(sw), 1)
        result[code] = {'similarity': round(ratio, 3), 'word_cover': round(cover, 3),
                        'html_len': len(skel), 'orig_len': len(orig)}
        flag = 'OK' if ratio >= 0.85 else ('проверить' if ratio >= 0.6 else 'пересобрать')
        md.append('- **№%s `%s`** — сходство %.0f%%, покрытие слов %.0f%% — %s'
                  % (r['doc_index'] or '—', code, ratio * 100, cover * 100, flag))
        if flag != 'OK':
            bad.append((code, flag, ratio))
            sw_only = sorted(list(sw - ow))[:12]
            md.append('  - слова шаблона, которых нет в оригинале: %s' % (', '.join(sw_only) or '—'))
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    OUT_MD.write_text('\n'.join(md) + '\n', encoding='utf-8')
    print('сверка:', OUT_MD)
    print('документов проверено:', len(result), '| требуют внимания:', len(bad))
    for code, flag, ratio in sorted(bad, key=lambda x: x[2]):
        print('   %-38s %-12s %.0f%%' % (code, flag, ratio * 100))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
