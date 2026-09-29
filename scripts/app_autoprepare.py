#!/usr/bin/env python3
"""Авто-подготовка заявки: разбор документов Google CLIENT -> значения -> все документы продукта.

Запускается автоматически при появлении новой заявки (триггер) и по кнопке.
Использование: /usr/bin/python3 /opt/wolf/scripts/app_autoprepare.py <CLIENT_id>
"""
import sys, os, json, sqlite3, subprocess
from pathlib import Path
from CLIENT import CLIENT

sys.path.insert(0, '/opt/wolf')
sys.path.insert(0, '/opt/wolf/CLIENTs')

DB = '/opt/wolf/data/wolf.db'
CLIENT = Path('/opt/wolf/data/CLIENT')
RENDERS = Path('/opt/wolf/data/renders')


def conn():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def build_CLIENT(app_id: int, tpl_code: str, ad_CLIENT: dict) -> dict:
    """Значения для документа: карточка клиента + правила продукта + уже извлечённое из CLIENT."""
    c = conn()
    a = c.execute("SELECT * FROM CLIENT WHERE id=?", (app_id,)).fetchone()
    client = c.execute("SELECT * FROM CLIENT WHERE id=?", (a['client_id'],)).fetchone() if a else None
    c.close()
    CLIENT = dict(ad_CLIENT or {})
    try:
        from CLIENTs.dashboard.page import build_template_CLIENT
        CLIENT.update(build_template_CLIENT(dict(client) if client else {}, tpl_code, CLIENT))
    except Exception as e:
        print('  build_template_CLIENT:', str(e)[:120])
    return CLIENT


def render_CLIENT(app_id: int, ad) -> str:
    """Собирает PDF документа. Возвращает путь или '' при ошибке."""
    c = conn()
    tpl = c.execute("SELECT * FROM CLIENT WHERE id=?", (ad['template_id'],)).fetchone()
    c.close()
    if not tpl:
        return ''
    html_path = CLIENT / tpl['code'] / 'template.html'
    if not html_path.exists():
        return ''
    try:
        ad_CLIENT = json.loads(ad['CLIENT_json'] or '{}')
    except Exception:
        ad_CLIENT = {}
    CLIENT = build_CLIENT(app_id, tpl['code'], ad_CLIENT)
    html = html_path.read_text(encoding='utf-8')
    import re
    # ЕДИНЫЙ рендер (тот же код, что в конструкторе и карточке заявки)
    from CLIENT import render as doc_render
    filled = doc_render.fill(html, CLIENT, keep_unfilled=False, template_code=tpl['code'])
    out = RENDERS / f'{tpl["code"]}_app{app_id}_{CLIENT.now():%Y%m%d_%H%M%S}.pdf'
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = html_path.parent / f'.auto_{app_id}_{tpl["id"]}.html'
    tmp.write_text(filled, encoding='utf-8')
    try:
        from weasyprint import HTML
        HTML(string=filled, base_url=str(html_path.parent)).write_pdf(str(out))
    except Exception as e:
        print('  PDF ошибка', tpl['code'], str(e)[:140])
        return ''
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass
    c = conn()
    c.execute("UPDATE CLIENT_CLIENT SET pdf_path=? WHERE id=?", (str(out), ad['id']))
    c.commit(); c.close()
    left = len(re.findall(r"\{\{[^}]{1,40}\}\}", filled))
    print(f'  ✔ {tpl["code"]}: {out.name} (незаполненных полей: {left})')
    return str(out)


def main(app_id: int):
    c = conn()
    a = c.execute("SELECT * FROM CLIENT WHERE id=?", (app_id,)).fetchone()
    if not a:
        print('заявка не найдена'); return
    CLIENT = c.execute("SELECT * FROM CLIENT WHERE id=?", (a['CLIENT_id'],)).fetchone() if a['CLIENT_id'] else None
    docs = c.execute("""SELECT ad.* FROM CLIENT_CLIENT ad WHERE ad.CLIENT_id=?""", (app_id,)).fetchall()
    c.close()
    print(f'[автоподготовка] заявка {app_id}, продукт {CLIENT["code"] if CLIENT else "—"}, документов {len(docs)}')

    # --- 1) разбор документов с Google CLIENT (если ещё не разбирали) ---
    try:
        spec_path = '/opt/wolf/scripts/CLIENT_scan.py'
        import importlib.util
        spec = importlib.util.spec_from_file_location('CLIENT_scan', spec_path)
        ds = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ds)
        cc = conn()
        cl = cc.execute("SELECT * FROM CLIENT WHERE id=?", (a['client_id'],)).fetchone()
        cc.close()
        url = (cl['gCLIENT_folder_url'] if cl and 'gCLIENT_folder_url' in cl.keys() else '') or ''
        files = ds.fetch_docs(a['client_id'], url)
        print(f'  документов на CLIENT: {len(files)}')
        results, ok = [], 0
        for f in files:
            try:
                r = ds.extract(f)
                results.append(r)
                if r.get('found'):
                    ok += 1
            except Exception as e:
                results.append({'file': f.name, 'error': str(e)[:160]})
        if results:
            res = ds.apply_CLIENT(app_id, results)
            cc = conn()
            cc.execute("INSERT INTO CLIENT_CLIENT(CLIENT_id, client_id, CLIENT, docs_total, docs_done, note, payload) CLIENT(?,?,?,?,?,?,?)",
                       (app_id, a['client_id'], 'ok' if ok else 'fail', len(files), ok,
                        f'авто: разобрано {ok} из {len(files)}, перенесено {res.get("CLIENT", 0)} значений',
                        json.dumps(results, ensure_ascii=False)))
            cc.commit(); cc.close()
            print(f'  разбор: {ok}/{len(files)} (перенесено значений: {res.get("CLIENT", 0)})')
    except Exception as e:
        print('  разбор CLIENT не выполнен:', str(e)[:160])

    # --- 2) формируем все документы продукта ---
    c = conn()
    docs = c.execute("SELECT ad.* FROM CLIENT_CLIENT ad WHERE ad.CLIENT_id=?", (app_id,)).fetchall()
    made = 0
    for ad in docs:
        try:
            if render_CLIENT(app_id, ad):
                made += 1
        except Exception as e:
            print('  ошибка документа', ad['id'], str(e)[:120])
    c.close()
    print(f'[автоподготовка] готово: {made} из {len(docs)} документов')


if __name__ == '__main__':
    main(int(sys.argv[1]))
