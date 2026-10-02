-- Word frequencies from video titles (category x period)
-- type NULL on insert
-- backfill: -1 leaving, 0 core, 1 new, 2 both

CREATE TABLE IF NOT EXISTS wordstat (
    id SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL,
    period DATE NOT NULL,
    lexeme TEXT NOT NULL,
    word TEXT NOT NULL,
    freq INTEGER NOT NULL,
    type SMALLINT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_wordstat_cat_period_lexeme UNIQUE (category_id, period, lexeme)
);

CREATE INDEX IF NOT EXISTS idx_wordstat_cat_period
    ON wordstat (category_id, period);

CREATE INDEX IF NOT EXISTS idx_wordstat_cat_period_type
    ON wordstat (category_id, period, type);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_set_updated_at_wordstat ON wordstat;

CREATE TRIGGER trigger_set_updated_at_wordstat
BEFORE UPDATE ON wordstat
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
