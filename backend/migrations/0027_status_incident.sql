-- 0027_status_incident.sql
-- Public status-page incident banner. One row is "active" at a time — the
-- admin creates/updates it via POST /admin/status/incident and clears it via
-- DELETE. /status/summary reads the active row (if any) alongside the Kuma
-- heartbeat data. Additive only.

CREATE TABLE IF NOT EXISTS status_incident (
    id          BIGSERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    severity    TEXT NOT NULL DEFAULT 'warning'
                CHECK (severity IN ('info', 'warning', 'critical')),
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_status_incident_active ON status_incident (active) WHERE active;
