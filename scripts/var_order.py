#!/usr/bin/env python3
"""Порядок переменных документа: сверху вниз, слева направо (как в HTML-шаблоне).

Координаты берём из absolute-блоков (left/top в pt), вложенные — складываем.
Если у нескольких переменных координаты совпадают (одна строка), порядок задаёт
их появление внутри строки. Именно этот порядок используется в левой панели
конструктора, поэтому список полей идёт вслед за документом.
"""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

HTML_DIR = Path('/opt/wolf_v2/data/templates')


class OrderParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.found = {}
        self.seq = 0

    @staticmethod
    def _pos(style: str):
        top = re.search(r'top:\s*(-?[\d.]+)pt', style)
        left = re.search(r'left:\s*(-?[\d.]+)pt', style)
        if top and left:
            return float(top.group(1)), float(left.group(1))
        return None

    def handle_starttag(self, tag, attrs):
        pos = self._pos(dict(attrs).get('style') or '')
        base = self.stack[-1][:2] if self.stack else (0.0, 0.0)
        self.stack.append((base[0] + pos[0], base[1] + pos[1]) if pos else base)
        for _k, v in attrs:
            if not v or '{{' not in v:
                continue
            for m in re.finditer(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}', v):
                nm = m.group(1)
                if nm in self.found:
                    continue
                self.seq += 1
                self.found[nm] = (round(self.stack[-1][0], 1), round(self.stack[-1][1], 1), self.seq)

    def handle_endtag(self, tag):
        if self.stack:
            self.stack.pop()

    def handle_data(self, data):
        top, left = self.stack[-1] if self.stack else (0.0, 0.0)
        for m in re.finditer(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}', data):
            nm = m.group(1)
            if nm in self.found:
                continue
            self.seq += 1
            self.found[nm] = (round(top, 1), round(left, 1), self.seq)


def order_for(code: str) -> list[str]:
    f = HTML_DIR / code / 'template.html'
    if not f.exists():
        return []
    p = OrderParser()
    p.feed(f.read_text(encoding='utf-8', errors='ignore'))
    return [n for n, _ in sorted(p.found.items(), key=lambda kv: kv[1])]


if __name__ == '__main__':
    codes = sys.argv[1:] or sorted(d.name for d in HTML_DIR.iterdir() if d.is_dir())
    for c in codes:
        names = order_for(c)
        print(f'{c[:36]:36} {len(names)}: ' + (', '.join(names) if names else '— переменных нет'))
