-- Индексы под реальные запросы админки и бота.
-- По этим полям идут выборки чаще всего: application_id (14 мест в коде),
-- template_id (10), status, client_id. До этого индексов на этих таблицах не было.
CREATE INDEX IF NOT EXISTS idx_app_client        ON applications(client_id);
CREATE INDEX IF NOT EXISTS idx_app_status        ON applications(status);
CREATE INDEX IF NOT EXISTS idx_app_client_status ON applications(client_id, status);
CREATE INDEX IF NOT EXISTS idx_adoc_app          ON application_documents(application_id);
CREATE INDEX IF NOT EXISTS idx_adoc_tpl          ON application_documents(template_id);
CREATE INDEX IF NOT EXISTS idx_adoc_app_tpl      ON application_documents(application_id, template_id);
CREATE INDEX IF NOT EXISTS idx_tvar_tpl          ON template_variables(template_id);
