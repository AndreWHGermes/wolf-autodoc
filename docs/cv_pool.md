# Резюме (CV) для Wolf AutoDoc — паттерны, пул должностей, правила автогенерации

Источники (реальные данные, не выдумка):
- `docs/cv_corpus.md` — 2 реальных резюме клиентов из архива (Anna CLIENT, CLIENT CLIENT)
- три шаблона системы: `cv__format_short` (#4), `cv__format_detailed` (#5), `cv__format_CLIENT` (#6)
- 9 заявок с заполненным полем должности (остальные 63 — пусто)

---

## 1. Структура резюме (что реально пишется)

Единый каркас во всех образцах:

1. **Шапка**: имя (капсом), профессия/должность, Nationality, Date of Birth, иногда phone / email / current location
2. **Профиль**: `PROFILE` или `CORE COMPETENCIES` — 1 абзац (2–3 предложения) либо 3 пункта
3. **Опыт**: `PROFESSIONAL EXPERIENCE` / `WORK EXPERIENCE` — по каждому месту:
   - Компания — Должность
   - Период (`September 2025 – Present`, `2020 – 2024`)
   - Локация (`South San Francisco, CA, USA (remote)`)
   - **4–5 пунктов обязанностей** — это основной объём текста
4. **Навыки / образование**: `SKILLS`, `CORE COMPETENCIES`, языки

## 2. Паттерны формулировок (дословно из архива)

**Профиль** — формула:
> `<Профессия> professional with over <N> years of experience across <область>. Skilled in <навык 1>, <навык 2>, and <навык 3>.`

Пример: «Social media and video production professional with over six years of experience across SMM agency and in-house production environments. Skilled in content planning, cross-platform social media production, and coordinating remote creative teams from concept through publication.»

**Пункты обязанностей** — 1 строка, начинается с глагола, заканчивается точкой, без «я»:
> Plan, produce, and coordinate … / Manage … / Oversee … / Coordinate … / Ensure … / Develop and execute … / Monitor … / Administer …

Рабочие примеры из архива:
- «Plan, produce, and coordinate video and social media content across the company's platforms.»
- «Manage content calendars and production schedules, coordinating with creative and editing teams.»
- «Oversee pre-production, filming logistics, and post-production/editing workflows.»
- «Coordinate remote production operations and ensure timely delivery of content.»
- «Developing and executing HR strategy, and managing full-cycle recruitment for key technical positions.»
- «Administering the company's internal IT infrastructure, access management, and software systems.»
- «Coordinating distributed remote workflows and providing high-level administrative support.»

**Обязательный акцент для визы**: работа **удалённая** и на компанию за пределами Индонезии — в тексте должны быть слова `remote`, `distributed team`, `cross-timezone`, `cross-platform`.

## 3. Пул должностей (RU / EN) и блоки описания

Формируется из: реальных должностей в заявках (Product Manager, Director, Fashion Designer, Marketing Director, IT Specialist, Existing Client Account Manager, Social Media Producer / Creative Producer, Infrastructure Engineer) + типовые профессии клиентов на визы D12 / E33G.

По каждой должности — три блока описания (объём под формат резюме):

**1. Администратор / Administrative Assistant / Office Manager**
- короткий: «Provide personal and administrative assistance to the client, including calendar management, correspondence, and travel arrangements.»
- средний: «Manage executive calendars, schedule meetings and travel, and handle correspondence on behalf of the client. Maintain filing systems and process documentation, ensuring accuracy and confidentiality. Coordinate with vendors and service providers for day-to-day office needs.»
- развёрнутый (+ навыки): «Provide comprehensive administrative support: manage executive calendars across time zones, plan business travel and itineraries, and handle incoming correspondence. Maintain document flow and filing systems, prepare reports and presentations. Coordinate suppliers, contractors and service providers. Process payments and track expenses against budget.» + Microsoft Office, Google Workspace, CRM, деловая переписка, тайм-менеджмент

**2. Менеджер по продажам / Sales Manager / Account Manager**
- короткий: «Manage the existing client portfolio and drive repeat sales through regular account communication.»
- средний: «Manage existing client accounts, negotiate terms and prepare commercial proposals. Track the sales pipeline and report on performance. Build long-term relationships with key clients to grow repeat business.»
- развёрнутый: «Own the full sales cycle from first contact to contract signature. Develop and maintain relationships with key accounts, negotiate pricing and terms, and prepare commercial proposals. Track pipeline in CRM and report weekly performance against targets. Coordinate with logistics and finance to ensure timely delivery and payment. Identify upsell opportunities within the existing client base.» + CRM (Bitrix24/amoCRM), переговоры, коммерческие предложения, Excel, B2B

**3. Маркетолог / Marketing Specialist / Marketing Director**
- короткий: «Plan and run marketing campaigns across digital channels to promote the company's products.»
- средний: «Develop marketing strategy across digital channels, run advertising campaigns and monitor their performance. Prepare content plans and coordinate designers and copywriters. Analyse metrics and report results to management.»
- развёрнутый: «Develop and execute the marketing strategy for the company's products across digital channels. Plan and run advertising campaigns, monitor budgets, and optimise performance against KPIs. Coordinate content production with designers, copywriters and video teams. Analyse traffic, conversion and retention metrics, and prepare regular performance reports. Run email and social media communications and manage the brand presence.» + Google Ads / Meta Ads, аналитика, SMM, e-mail-маркетинг, воронки

**4. SMM / Social Media Producer / Creative Producer**
- короткий: «Produce video and social media content across the company's platforms, from planning to publication.»
- средний: «Plan, produce and coordinate video and social media content across the company's platforms. Manage content calendars and production schedules, coordinating with creative and editing teams. Monitor platform analytics and prepare performance reports.»
- развёрнутый: «Plan, produce, and coordinate video and social media content across the company's platforms. Manage content calendars and production schedules, coordinating with creative and editing teams. Oversee pre-production, filming logistics, and post-production/editing workflows. Coordinate remote production operations and ensure timely delivery of content. Monitor platform analytics and prepare performance reports to inform content strategy.» + Instagram, YouTube, TikTok, монтаж, контент-план, аналитика

**5. HR / Рекрутер / Head of HR**
- короткий: «Manage recruitment and HR processes, including onboarding and personnel records.»
- средний: «Run full-cycle recruitment for key positions, from sourcing to offer. Maintain personnel records and HR documentation, and support onboarding of new employees. Coordinate distributed remote workflows and internal communications.»
- развёрнутый: «Develop and execute HR strategy, and manage full-cycle recruitment for key technical positions. Administer internal systems, access management and HR documentation. Coordinate distributed remote workflows and provide administrative support to team members. Ensure compliance with internal regulations and HR guidelines.» + рекрутинг, HR-документооборот, ATS, онбординг, 1С/HRM

**6. IT-специалист / IT Specialist / Infrastructure Engineer**
- короткий: «Maintain the company's IT infrastructure, user accounts and internal systems.»
- средний: «Administer the company's IT infrastructure, access rights and software systems. Provide technical support to employees and resolve incidents. Maintain backup and monitoring processes.»
- развёрнутый: «Administer the company's internal IT infrastructure, access management, and software systems. Provide technical support to employees, resolve incidents and maintain documentation. Configure and maintain servers, network services, and backup processes. Monitor system availability and security, and apply updates in line with company policies.» + Windows/Linux, AD, сети, backup, мониторинг

**7. Дизайнер / Designer / Fashion Designer**
- короткий: «Develop design concepts and prepare technical documentation for production.»
- средний: «Develop collection concepts and prepare technical drawings and specifications for production. Work with suppliers on materials and samples. Maintain the design archive and documentation.»
- развёрнутый: «Develop design concepts from research to production-ready documentation. Prepare technical drawings, specifications and material lists, and supervise sampling with suppliers. Coordinate with manufacturers to ensure quality and deadlines. Maintain the design archive, mood boards and documentation.» + Adobe (Illustrator/Photoshop), конструирование, работа с поставщиками

**8. Бухгалтер / Accountant**
- короткий: «Maintain primary accounting records, process invoices and prepare reports.»
- средний: «Maintain primary accounting documentation, process invoices and payments, and prepare periodic reports. Track accounts receivable and payable, and support tax reporting.»
- развёрнутый: «Maintain primary accounting records, process invoices, payments and reconciliation. Prepare periodic financial and tax reports in line with requirements. Track accounts receivable/payable and control budget execution. Interact with counterparties and support audits.» + 1С, Excel, налоговая отчётность

**9. Водитель / Driver**
- короткий: «Provide safe and timely transportation, including route planning and vehicle upkeep.»
- средний: «Provide personal and business transportation, plan routes and monitor vehicle condition. Maintain trip documentation and coordinate servicing.»
- развёрнутый: «Provide safe and timely transportation for the client and business needs, including route planning and schedule coordination. Monitor the technical condition of the vehicle and arrange maintenance. Maintain trip documentation and ensure compliance with traffic regulations.» + категории B/C, маршруты, обслуживание

**10. Няня / Nanny / Childcare Specialist**
- короткий: «Provide childcare, ensuring safety, daily routines and developmental activities.»
- средний: «Provide full-day childcare: daily routines, meals, walks and developmental activities. Organise age-appropriate games and lessons, and maintain a safe environment.»
- развёрнутый: «Provide comprehensive childcare, including daily routines, nutrition, and developmental activities. Organise educational games, reading and creative sessions appropriate to the child's age. Maintain a safe and clean environment, and coordinate with parents on the daily schedule and progress.» + первая помощь, развивающие методики, английский

**11. Продавец / Retail Sales / Store Manager**
- короткий: «Serve customers, process sales and maintain the store's product display.»
- средний: «Advise customers on products, process sales and maintain the product display. Track stock availability and prepare orders to suppliers.»
- развёрнутый: «Advise customers and drive sales in line with store targets. Process transactions, maintain the product display, and monitor stock levels. Coordinate deliveries and supplier orders, and prepare daily sales reports.» + касса, мерчандайзинг, 1С/склад, клиентский сервис

**12. Логист / Logistics Manager**
- короткий: «Coordinate deliveries, shipments and supplier communications.»
- средний: «Coordinate shipments and deliveries, prepare transport documentation and monitor deadlines. Communicate with carriers, warehouses and suppliers.»
- развёрнутый: «Coordinate inbound and outbound shipments, select carriers and monitor delivery deadlines. Prepare transport and customs documentation, and control costs against budget. Communicate with warehouses, carriers and suppliers to resolve deviations in real time.» + ВЭД, ТТН, 1С/склад, таможня

**13. Преподаватель / репетитор / Tutor / Teacher**
- короткий: «Deliver online lessons and prepare individual study plans for students.»
- средний: «Deliver online lessons, prepare individual study plans and learning materials. Track student progress and provide feedback to parents or students.»
- развёрнутый: «Deliver online lessons in line with an individual study plan, and prepare learning materials and assessments. Track student progress, maintain lesson records and adjust the programme based on results. Communicate regularly with students and their parents on progress.» + Zoom, интерактивные платформы, методики

**14. Повар / Chef / Cook**
- короткий: «Prepare dishes according to the menu, maintaining quality and hygiene standards.»
- средний: «Prepare dishes according to the menu and recipes, controlling quality and presentation. Maintain hygiene standards and monitor ingredient stock.»
- развёрнутый: «Prepare dishes according to the menu and recipes, ensuring consistent quality and presentation. Plan daily production and monitor ingredient stock, placing orders as needed. Maintain sanitation and food-safety standards, and train kitchen staff on procedures.» + технологические карты, HACCP, закупки

**15. Директор / General Director / Operations Manager**
- короткий: «Manage day-to-day company operations and coordinate key business processes.»
- средний: «Manage day-to-day operations across company departments, coordinate business processes and report to the owners. Control budgets and key contracts.»
- развёрнутый: «Manage day-to-day company operations and coordinate key business processes across departments. Control budgets, contracts and supplier relations, and prepare regular performance reports for the owners. Oversee hiring decisions and set operational priorities. Ensure business strategy, sales and supplier relations run in line with company targets.» + управление, бюджетирование, контракты, отчётность

**16. Product Manager / Project Manager**
- короткий: «Manage the product backlog and coordinate the delivery of key features.»
- средний: «Manage the product backlog and priorities, coordinate the team and control delivery deadlines. Gather requirements from stakeholders and report progress.»
- развёрнутый: «Own the product roadmap and manage the backlog and priorities. Gather requirements from stakeholders and translate them into specifications for the team. Coordinate delivery across departments and control deadlines and scope. Report progress and metrics to management, and adapt the plan based on results.» + Jira, аналитика, A/B, agile

## 4. Что должно подставляться по форматам

| Формат | Объём описания |
|---|---|
| Короткий (#4) | 1 место работы, 3–4 пункта обязанностей, без профиля (или 1 строка) |
| Сиваева (#6) | профиль 1 абзац + 2 места работы, 3–4 пункта каждое |
| Расширенный (#5) | профиль `cv_summary` + 2 места (`cv_job1_*`, `cv_job2_*`) по 4–5 пунктов + hard/soft skills, tools, языки |

## 5. Правила заполнения (решение Андрея)

1. **Приоритет — автогенерация** по паттернам из архива (текст собирается по формулам выше).
2. Если должность известна из карточки клиента — блок описания предлагается выпадающим списком под эту должность.
3. Если должности нет (сейчас у 63 из 72 клиентов) — администратор выбирает профессию из справочника.
4. Администратор всегда может: вписать текст руками, выбрать готовый вариант, взять из истории ранее использованных формулировок, открыть редактор поля и поправить сгенерированное.
5. Правка руками не перебивается автоматикой (флаг chosen).

## 6. Что нужно внедрить в систему

- Переменные описания в шаблоны #4 (короткий) и #6 (Сиваева) — сейчас там статичный текст.
- Справочник должностей + блоков описания (этот файл → данные в системе).
- Генератор: должность → тексты трёх объёмов (с подстановкой компании, периода, «remote»).
- UI в панели переменных: список вариантов по должности, кнопка «Сгенерировать», ручной ввод, история, редактор.
