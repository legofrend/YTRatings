-- Resume state for scenario runners (auto / close). Shared across hosts.
-- Browse: SELECT * FROM pipeline_run WHERE scenario='close' ORDER BY period, step_ord;
CREATE TABLE IF NOT EXISTS pipeline_run (
    id         bigserial   PRIMARY KEY,
    scenario   text        NOT NULL,
    period     date        NOT NULL,
    step_ord   int         NOT NULL,              -- 1-based order from YAML
    step_id    text        NOT NULL,
    status     text        NOT NULL DEFAULT 'pending',  -- pending|running|done|failed
    error      text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (scenario, period, step_id)
);
