-- Reference SQL for ReportDAO.refresh_channel_report().
-- Prefer:  python -m app.main channel-report
-- (uses app DATABASE_URL / async session)

DROP TABLE IF EXISTS channel_report;

CREATE TABLE channel_report AS
SELECT * FROM report_view;

CREATE INDEX IF NOT EXISTS idx_channel_report_cat_period_rank
  ON channel_report (category_id, report_period, rank);

CREATE INDEX IF NOT EXISTS idx_channel_report_channel_period
  ON channel_report (channel_id, report_period);

CREATE INDEX IF NOT EXISTS idx_channel_report_period
  ON channel_report (report_period);

ANALYZE channel_report;
