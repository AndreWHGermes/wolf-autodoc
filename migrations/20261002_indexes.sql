-- Индексы под реальные запросы админки и бота.
-- По этим полям идут выборки чаще всего: CLIENT_id (14 мест в коде),
-- template_id (10), CLIENT, client_id. До этого индексов на этих таблицах не было.
CREATE CLIENT IF NOT EXISTS idx_app_client        ON CLIENT(client_id);
CREATE CLIENT IF NOT EXISTS idx_app_status        ON CLIENT(CLIENT);
CREATE CLIENT IF NOT EXISTS idx_app_client_status ON CLIENT(client_id, CLIENT);
CREATE CLIENT IF NOT EXISTS idx_adoc_app          ON CLIENT_CLIENT(CLIENT_id);
CREATE CLIENT IF NOT EXISTS idx_adoc_tpl          ON CLIENT_CLIENT(template_id);
CREATE CLIENT IF NOT EXISTS idx_adoc_app_tpl      ON CLIENT_CLIENT(CLIENT_id, template_id);
CREATE CLIENT IF NOT EXISTS idx_tvar_tpl          ON template_CLIENT(template_id);
