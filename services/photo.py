"""Подготовка фото клиента для документов Wolf.

Фотография с телефона (например 900x1600) в фото-слот резюме не влезает: в
шаблоне слот 141.15 x 197.30 pt — это пропорция 5:7. Если положить снимок как
есть, браузер растянет его и лицо поедет.

Поэтому фото приводится к пропорции слота: лишний фон обрезается сверху и
снизу (голова при этом остаётся в кадре — сдвиг кадрирования по умолчанию
смещён вверх), картинка уменьшается до печатного размера и сохраняется в
data/client_photos. Результат кэшируется: повторная генерация не пересчитывает
фото, если исходник не менялся.

Настройки кадрирования (сдвиг по вертикали и зум) хранятся в таблице
client_photo_crop — их меняет мини-редактор фото в панели переменных.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sqlite3
import time

# Пропорция фото-слота в резюме: 141.15 x 197.30 pt
DEFAULT_RATIO = (5, 7)
DEFAULT_WIDTH = 700  # 700 x 980 px — с запасом под печать A4

BASE = pathlib.Path("/opt/wolf_v2")
OUT_DIR = BASE / "data" / "client_photos"
DB_PATH = BASE / "data" / "wolf.db"


def _db():
    con = sqlite3.connect(str(DB_PATH), timeout=10)
    con.row_factory = sqlite3.Row
    return con


def ensure_schema() -> None:
    """Таблица настроек кадрирования: сдвиг по вертикали, зум, пропорция."""
    try:
        con = _db()
        con.execute(
            "CREATE TABLE IF NOT EXISTS client_photo_crop ("
            " client_id INTEGER PRIMARY KEY,"
            " ratio_w INTEGER DEFAULT 5,"
            " ratio_h INTEGER DEFAULT 7,"
            " crop_y REAL DEFAULT 0.35,"   # 0 — верх кадра, 1 — низ
            " zoom REAL DEFAULT 1.0,"
            " src_hash TEXT,"
            " updated_at TEXT)")
        con.commit()
        con.close()
    except Exception:
        pass


def crop_settings(client_id) -> dict:
    """Настройки кадрирования клиента: по умолчанию сдвиг вверх (голова в кадре)."""
    out = {"ratio_w": DEFAULT_RATIO[0], "ratio_h": DEFAULT_RATIO[1],
           "crop_y": 0.35, "zoom": 1.0}
    try:
        con = _db()
        row = con.execute("SELECT * FROM client_photo_crop WHERE client_id=?",
                          (client_id,)).fetchone()
        con.close()
        if row:
            out["ratio_w"] = int(row["ratio_w"] or out["ratio_w"])
            out["ratio_h"] = int(row["ratio_h"] or out["ratio_h"])
            out["crop_y"] = float(row["crop_y"] if row["crop_y"] is not None else out["crop_y"])
            out["zoom"] = float(row["zoom"] or out["zoom"])
    except Exception:
        pass
    return out


def save_crop_settings(client_id, crop_y: float, zoom: float, ratio=None) -> dict:
    """Сохранить настройки кадрирования (вызывает редактор фото)."""
    ensure_schema()
    rw, rh = ratio or DEFAULT_RATIO
    try:
        cy = min(1.0, max(0.0, float(crop_y)))
        zm = min(3.0, max(1.0, float(zoom)))
    except Exception:
        cy, zm = 0.35, 1.0
    try:
        con = _db()
        con.execute(
            "INSERT INTO client_photo_crop (client_id, ratio_w, ratio_h, crop_y, zoom, updated_at)"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(client_id) DO UPDATE SET crop_y=?, zoom=?, ratio_w=?, ratio_h=?, updated_at=?",
            (client_id, rw, rh, cy, zm, time.strftime("%Y-%m-%d %H:%M:%S"),
             cy, zm, rw, rh, time.strftime("%Y-%m-%d %H:%M:%S")))
        con.commit()
        con.close()
    except Exception:
        pass
    return {"ratio_w": rw, "ratio_h": rh, "crop_y": cy, "zoom": zm}


def _hash_file(path) -> str:
    try:
        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:12]
    except Exception:
        return ""


def prepare_photo(src, client_id=None, ratio=None, width: int = DEFAULT_WIDTH,
                  crop_y: float = None, zoom: float = None) -> str:
    """Обрезать фото по пропорции слота, уменьшить и сохранить копию.

    Возвращает путь к готовому файлу. Если что-то не получилось — исходный путь,
    чтобы документ в любом случае собрался.
    """
    try:
        from PIL import Image, ImageOps
    except Exception:
        return str(src)

    s = pathlib.Path(str(src))
    if not s.exists():
        return str(src)

    st = crop_settings(client_id) if client_id else {}
    if ratio:
        rw, rh = int(ratio[0]), int(ratio[1])
    else:
        rw = int(st.get("ratio_w") or DEFAULT_RATIO[0])
        rh = int(st.get("ratio_h") or DEFAULT_RATIO[1])
    cy = float(st.get("crop_y", 0.35) if crop_y is None else crop_y)
    zm = float(st.get("zoom", 1.0) if zoom is None else zoom)

    key = "%s|%s|%s|%s|%s" % (_hash_file(s), rw, rh, round(cy, 3), round(zm, 3))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / ("client_%s_%s_%s.jpg" % (client_id or "x", "%dx%d" % (rw, rh),
                                              hashlib.sha1(key.encode()).hexdigest()[:8]))
    if out.exists() and out.stat().st_size > 1000:
        return str(out)

    try:
        im = Image.open(str(s))
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")

        # зум: сначала расширяем кадр от центра, потом обрезаем по пропорции
        if zm > 1.001:
            w0, h0 = im.size
            nw, nh = int(w0 * zm), int(h0 * zm)
            im = im.resize((nw, nh), Image.LANCZOS)
            left = (nw - w0) // 2
            top = max(0, int((nh - h0) * cy))
            im = im.crop((left, top, left + w0, top + h0))

        w, h = im.size
        target = rw / float(rh)
        cur = w / float(h)
        if cur > target:
            # шире слота — режем боками
            nw = int(round(h * target))
            left = max(0, (w - nw) // 2)
            im = im.crop((left, 0, left + nw, h))
        else:
            # выше слота — режем фон сверху и снизу (сдвиг задаёт, где оставить)
            nh = int(round(w / target))
            top = int(round((h - nh) * cy))
            top = max(0, min(h - nh, top))
            im = im.crop((0, top, w, top + nh))

        # печатный размер: ширина задана, высота по пропорции
        out_h = int(round(width * rh / float(rw)))
        im = im.resize((int(width), out_h), Image.LANCZOS)
        im.save(str(out), "JPEG", quality=90, optimize=True)
        return str(out)
    except Exception:
        return str(src)


def preview_data_url(src, client_id=None, ratio=None, max_width: int = 320) -> str:
    """Небольшое превью фото (data URL) — для редактора кадрирования."""
    try:
        import base64
        import io
        from PIL import Image, ImageOps
        st = crop_settings(client_id) if client_id else {}
        rw = int(st.get("ratio_w") or DEFAULT_RATIO[0])
        rh = int(st.get("ratio_h") or DEFAULT_RATIO[1])
        im = ImageOps.exif_transpose(Image.open(str(src))).convert("RGB")
        w, h = im.size
        nh = int(round(max_width * h / float(w)))
        im = im.resize((max_width, nh), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""
