#!/usr/bin/env python3
"""Прописывает в базе правило сборки резюме (требование Андрея, 17.10.2026)."""
import sqlite3

RULE = (
    "Порядок: 1) профессия/должность — из документов клиента и заявки, затем из карточки; "
    "2) если нет — удалённая профессия из пула (remote_professions.json); "
    "3) организация — из договора (та же, что в документе №11), иначе реальная организация "
    "из пула (organizations.json) с ИНН, адресом и ФИО генерального директора, город Москва "
    "или Санкт-Петербург; 4) обязанности и навыки — по должности/отрасли (cv_content.py); "
    "5) предыдущее место — другая реальная организация из пула, срок на 5 лет раньше. "
    "Данные клиента всегда сильнее пула."
)

c = sqlite3.connect('/opt/wolf_v2/data/wolf.db')
tid = c.execute("SELECT id FROM templates WHERE code='cv__format_sivaev'").fetchone()[0]
names = ('cv_profession', 'cv_job1_title', 'cv_job1_company', 'cv_job1_period', 'cv_job1_bullets',
         'cv_job2_title', 'cv_job2_company', 'cv_job2_period', 'cv_job2_bullets',
         'cv_skills_hard', 'cv_skills_soft', 'cv_summary')
n = 0
for name in names:
    cur = c.execute('SELECT rule_text FROM template_variables WHERE template_id=? AND name=?',
                    (tid, name)).fetchone()
    if not cur:
        continue
    old = cur[0] or ''
    if RULE in old:
        continue
    c.execute('UPDATE template_variables SET rule_text=? WHERE template_id=? AND name=?',
              ((old + '\n' + RULE).strip(), tid, name))
    n += 1
c.commit()
print('правило записано в переменных:', n)
