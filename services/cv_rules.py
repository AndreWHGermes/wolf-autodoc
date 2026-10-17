#!/usr/bin/env python3
"""Правило сборки резюме (требование Андрея, 17.10.2026).

Порядок взятия данных:
 1. Профессия/должность — из документов клиента и заявки (brief), затем из карточки.
 2. Нет профессии — берём удалённую профессию из пула (`remote_professions.json`).
 3. Организация — та, что указана у клиента; нет — реальная организация из пула
    (`organizations.json`) с ИНН, адресом и ФИО генерального директора; город —
    Москва или Санкт-Петербург.
 4. Обязанности и навыки — по должности/отрасли из `cv_content.py`, чтобы резюме
    читалось как у человека, который давно и стабильно работает в этой компании.
 5. Предыдущее место — другая реальная организация из пула, срок на 5 лет раньше.

Модуль только заполняет ПУСТЫЕ поля: данные клиента и заявки всегда сильнее пула.
"""
from __future__ import annotations

from datetime import date

CITIES = ('Moscow', 'Saint Petersburg')


def _org_name(org: dict) -> str:
    from services import org_pool
    return (org_pool.name_in_documents(org) or org.get('name_lat') or org.get('name') or '').strip()


def _pick_profession(client: dict, vals: dict) -> tuple[str, str]:
    from services import org_pool
    prof = str(vals.get('cv_profession') or '').strip()
    if not prof:
        prof = str((client or {}).get('position') or '').strip()
    if prof:
        return prof, org_pool.sector_of_profession(prof)
    pool = org_pool.remote_professions() or {}
    sector = str((client or {}).get('sector') or '').strip()
    items = pool.get(sector) if sector else None
    if not items:
        items = next(iter(pool.values()), [])
    prof = str(items[0]).strip() if items else 'Manager'
    return prof, org_pool.sector_of_profession(prof) or sector


def _org_for(profession: str, client: dict, app_id, exclude: str = '') -> str:
    """Реальная организация из пула: ИНН, адрес, директор. Москва/СПб."""
    from services import org_pool
    given = str((client or {}).get('company_name') or '').strip()
    if given and given.lower() != exclude.lower():
        return given
    # Компания договора: в резюме должна стоять та же организация, что в контракте
    try:
        pack = org_pool.for_application(client or {}, app_id) or {}
        name = _org_name(pack.get('org') or {})
        if name and name.lower() != exclude.lower():
            return name
    except Exception:
        pass
    for city in ('',) + CITIES:
        try:
            org = org_pool.pick_for(profession=profession, city=city, app_id=app_id,
                                    require_details=True) or {}
        except TypeError:
            org = org_pool.pick_for(profession, city, app_id) or {}
        name = _org_name(org)
        if name and name.lower() != exclude.lower():
            return name
    return ''


def fill_cv(vals: dict, client: dict, app_id=None) -> dict:
    """Дополняет пустые поля резюме по правилу. Возвращает изменённые ключи."""
    from services import cv_content

    prof, sector = _pick_profession(client, vals)
    if not str(vals.get('cv_profession') or '').strip():
        vals['cv_profession'] = prof
    if not str(vals.get('cv_job1_title') or '').strip():
        vals['cv_job1_title'] = prof

    org1 = str(vals.get('cv_job1_company') or '').strip() or _org_for(prof, client, app_id)
    if org1 and not str(vals.get('cv_job1_company') or '').strip():
        vals['cv_job1_company'] = org1

    want = [k for k in ('cv_summary', 'cv_job1_bullets', 'cv_job1_period',
                        'cv_skills_hard', 'cv_skills_soft', 'cv_education_degree',
                        'cv_education_school', 'cv_education_years', 'cv_languages')
            if not str(vals.get(k) or '').strip()]
    if want:
        addr = str((client or {}).get('address_live') or (client or {}).get('address') or '')
        city = ('Санкт-Петербург' if 'петербург' in addr.lower()
                else 'Москва' if 'москв' in addr.lower() else '')
        gen = cv_content.build(want, profession=prof, sector=sector, org_name=org1,
                               app_id=app_id, signed=date.today(), city=city) or {}
        for k, v in gen.items():
            if not str(vals.get(k) or '').strip() and str(v or '').strip():
                vals[k] = v

    # Профиль: если пришёл машинный «Specialist professional…», переписываем под
    # профессию и компанию — резюме должно читаться как у человека, который давно
    # и стабильно работает в этой организации.
    cur = str(vals.get('cv_summary') or '').strip()
    if not cur or cur.lower().startswith('specialist professional'):
        pack = cv_content.BY_SECTOR.get(sector or '', cv_content._DEFAULT)
        tail = ''
        if org1:
            tail = ' Currently works remotely as %s at %s.' % (prof, org1)
        else:
            tail = ' Currently works remotely as %s.' % prof
        vals['cv_summary'] = pack['summary'].rstrip('.').strip() + '.' + tail

    # Предыдущее место работы: другая реальная организация, срок на 5 лет раньше
    if not str(vals.get('cv_job2_company') or '').strip():
        org2 = _org_for(prof, {'company_name': ''}, None, exclude=org1)
        if org2:
            vals['cv_job2_company'] = org2
    if not str(vals.get('cv_job2_title') or '').strip():
        vals['cv_job2_title'] = 'Specialist'
    if not str(vals.get('cv_job2_bullets') or '').strip():
        pack = cv_content.BY_SECTOR.get(sector or '', cv_content._DEFAULT)
        vals['cv_job2_bullets'] = cv_content._bullets_for('', pack)
    if not str(vals.get('cv_job2_period') or '').strip():
        y = date.today().year
        vals['cv_job2_period'] = '%d — %d' % (y - 10, y - 5)
    return vals
