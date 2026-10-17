#!/usr/bin/env python3
"""Ищет заявки на договор, у которых организация есть в базе (для проверки печати/логотипа)."""
import sqlite3
import sys

sys.path.insert(0, '/opt/wolf_v2')
from services.values import build_template_values
from services.doc_branding import find_org

c = sqlite3.connect('/opt/wolf_v2/data/wolf.db')
c.row_factory = sqlite3.Row
rows = c.execute("""SELECT a.id, a.client_id FROM applications a
                    JOIN product_documents pd ON pd.product_id=a.product_id
                    JOIN templates t ON t.id=pd.template_id
                    WHERE t.code='employment_contract__default'
                    ORDER BY a.id DESC LIMIT 12""").fetchall()
for r in rows:
    cl = dict(c.execute('SELECT * FROM clients WHERE id=?', (r['client_id'],)).fetchone() or {})
    vals = build_template_values(cl, 'employment_contract__default', {}, r['id']) or {}
    org = find_org(vals)
    print(r['id'], '|', str(vals.get('employer_name'))[:34], '|',
          (org['name'] if org else 'нет в базе'), '| seal:', bool(org and org.get('seal_path')),
          '| logo:', bool(org and org.get('logo_path')))
