-- 0029_model_health_quarantine.sql
--
-- The health mirror used to have exactly two outcomes for a model whose
-- window looks bad: leave it alone, or write `availability = 'disabled'`.
-- That conflated two very different situations -- "this model is broken" and
-- "our account/quota currently can't reach it" (kr/* out of credit,
-- openrouter/*:free upstream quota exhausted, a gateway that is briefly
-- down) -- under one label that reads to an operator as "broken".
--
-- `health_quarantine_reason` distinguishes the two: NULL means this row was
-- never parked by the health mechanism (it may still be in `maintenance` for
-- an entirely different reason -- an admin hid it, discovery just found it,
-- or it has no price yet -- and none of those must ever be auto-promoted by
-- a probe). A non-NULL value is the provider-fault reason code (e.g.
-- 'http_402') that caused model_health.py to park the row instead of
-- disabling it, and is the ONLY case model_health.py is allowed to promote
-- back out of `maintenance` on its own once probes succeed again.
--
-- model_availability_change is the audit trail that bug 3 of the catalog
-- churn investigation found missing entirely: `model_catalog.updated_at`
-- was never touched by the health mirror, so nobody could see the catalog
-- shrinking and growing dozens of times a day. Every time the mirror
-- actually changes a row's availability, it now writes one row here.

ALTER TABLE model_catalog ADD COLUMN IF NOT EXISTS health_quarantine_reason TEXT;
ALTER TABLE model_catalog ADD COLUMN IF NOT EXISTS health_quarantined_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS model_availability_change (
    id BIGSERIAL PRIMARY KEY,
    model_id TEXT NOT NULL,
    from_availability TEXT,
    to_availability TEXT NOT NULL,
    -- Provider-fault reason code when the mirror parked the row, the last
    -- failing probe's error when it disabled one, NULL for a recovery.
    reason TEXT,
    health_status TEXT,
    success_rate DOUBLE PRECISION,
    sample_count INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_model_availability_change_time
    ON model_availability_change (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_availability_change_model_time
    ON model_availability_change (model_id, created_at DESC);
