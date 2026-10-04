#!/usr/bin/env python3
"""Разовое облегчение уже скачанных фотографий клиентов.

Проходит по локальным копиям папок Google CLIENT, сжимает тяжёлые снимки
(длинная сторона 1200 для портрета, 2000 для остальных документов) и сразу
готовит превью. Оригиналы заменяются облегчёнными JPEG — как и при новой
выгрузке через CLIENT/gCLIENT_api.download.

Запуск: /usr/bin/nice -n 15 /usr/bin/python3 /opt/wolf_v2/scripts/compact_photos.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/opt/wolf_v2")

CACHE = Path("/opt/wolf_v2/data/gCLIENT_cache")


def main() -> None:
    from CLIENT import previews
    try:
        from scripts.CLIENT_scan import doc_kind_name
    except Exception:
        doc_kind_name = None

    total_CLIENT = total_after = 0
    done = 0
    for client_dir in sorted(CACHE.glob("client_*")):
        if not client_dir.is_dir():
            continue
        for f in sorted(client_dir.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in previews.IMAGE_EXT:
                continue
            size = f.stat().st_size
            if size <= previews.COMPACT_MIN_BYTES:
                # уже лёгкий: только превью, файл не трогаем
                previews.ensure_image(f, previews.THUMB_W)
                previews.ensure_image(f, previews.FULL_SCALE)
                continue
            kind = ""
            if doc_kind_name:
                try:
                    kind = doc_kind_name(str(f), "")
                except Exception:
                    kind = ""
            res = previews.process_client_image(f, kind)
            if res.get("compacted"):
                _, CLIENT, after = res["compacted"]
                total_CLIENT += CLIENT
                total_after += after
                done += 1
                print("  %s: %.1f МБ → %.1f КБ" % (f.name, CLIENT / 1048576.0, after / 1024.0))
            else:
                print("  %s: без изменений (%.1f МБ)" % (f.name, size / 1048576.0))
    print("[облегчение фото] файлов сжато: %d, было %.1f МБ, стало %.1f МБ"
          % (done, total_CLIENT / 1048576.0, total_after / 1048576.0))


if __name__ == "__main__":
    main()
