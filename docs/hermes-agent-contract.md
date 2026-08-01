# Hermes agent daemon contract

This document specifies the HTTP contract between sanjhubai and the small daemon
that must run on a delivered Hermes server. **The daemon itself is not implemented
in this repository** — this is the spec an implementation must satisfy. Everything
below is served by `backend/hermes.py` under `/hermes/agent/*`.

## Provisioning

When an admin runs `POST /admin/hermes/orders/{order_id}/provision`, the response
includes two secrets, shown **exactly once**:

- `agent_token` — `hsa-<random>`, the daemon's credential for the endpoints below.
- `api_key` — `sk-<random>`, a normal Sanjhubai API key (same shape as
  `POST /api-keys`) scoped to the buyer's account, meant to be dropped into the
  daemon's LLM-calling config so Hermes' own model usage bills through the
  buyer's wallet via the existing `chat.py` reserve/settle path.

Both belong to the install script the admin runs on the box during delivery — they
are never re-shown, and neither is derivable from the dashboard afterward (the
dashboard only ever shows `agent_token_prefix`, never the token or its hash). If a
token is lost, the owner calls `POST /hermes/servers/{id}/rotate-agent-token` from
the dashboard and re-runs the install step with the new value.

## Auth

Every `/hermes/agent/*` request must carry:

```
Authorization: Bearer hsa-<token>
```

The server looks up the token by its salted hash (same `sha256(pepper + token)`
scheme as API keys, see `dependencies._hash_api_key`); an unknown or malformed
token gets `401`. There is no session cookie, no CSRF token, and no other header
required for these two endpoints.

## Polling loop

The daemon is expected to poll on a short interval (recommended: 30s) rather than
hold a persistent connection:

```
GET /hermes/agent/state
Authorization: Bearer hsa-<token>
X-Agent-Version: <daemon's own version string>   (optional)
```

Response:

```json
{
  "version": 3,
  "skills": [
    { "id": "coding", "manifest": {}, "options": {"languages": ["python", "go"]}, "enabled": true },
    { "id": "news-watch", "manifest": {}, "options": {"topics": ["ai", "iran-tech"], "schedule": "0 9 * * *"}, "enabled": true }
  ]
}
```

- `version` is `hermes_servers.desired_state_version` — it only ever increases. If
  it's unchanged since the daemon's last successful poll, there is nothing to do.
- `skills` is the **full desired state**, not a diff. The daemon should treat this
  as the complete list of skills that should exist on the box; anything installed
  locally but absent from this list should be removed.
- `manifest` is presently an unstructured JSON object per skill
  (`hermes_skill_catalog.manifest`) — the on-disk skill format/install mechanism
  isn't finalized yet, so this field is deliberately schema-free until that's
  decided. Treat it as opaque data to interpret however the daemon's skill
  installer expects.
- Calling this endpoint updates `last_heartbeat_at` and, if `X-Agent-Version` was
  sent, `agent_version` — this is how the dashboard's "last seen" and "in sync"
  indicators stay current. There is no separate heartbeat endpoint.

## Reporting results

After acting on a `state` response (or on its own periodic cadence), the daemon
reports what it actually did:

```
POST /hermes/agent/report
Authorization: Bearer hsa-<token>
Content-Type: application/json

{
  "version": 3,
  "results": [
    { "skill_id": "coding", "state": "installed" },
    { "skill_id": "news-watch", "state": "failed", "error": "cron install failed: permission denied" }
  ]
}
```

- `version` should be the `version` value from the `state` call the daemon just
  acted on. The server sets `hermes_servers.applied_state_version` to this value —
  that's what drives the dashboard's `in_sync` flag
  (`desired_state_version == applied_state_version`).
- `state` per skill is one of:
  - `installed` — the skill is present and enabled on the box.
  - `failed` — install/update attempted and failed; `error` should be a short,
    non-sensitive reason (never a stack trace or secret — this string is visible
    to the end user in the dashboard).
  - `removed` — confirms a skill that was marked `removing` (because the user
    deleted it, or disabled+never re-enabled it — see below) has actually been
    uninstalled from the box. **This is the only way the corresponding
    `hermes_server_skills` row is deleted server-side** — until the daemon
    confirms removal, the row stays with `state='removing'` so the dashboard can
    show "removal pending".
- Every report is also appended to `hermes_agent_events` for audit/debugging —
  there's no need for the daemon to log anything separately for sanjhubai's sake.
- This endpoint is idempotent to call repeatedly with the same payload; there's no
  harm in re-reporting the same state if a previous report's response was lost.

## What the dashboard user can trigger

These change `desired_state_version` (visible to the daemon on its next poll) but
never talk to the box directly:

- `POST /hermes/servers/{id}/skills` — attach a new skill. New row starts
  `state='pending'`.
- `PUT /hermes/servers/{id}/skills/{skill_id}` — change `options` and/or `enabled`.
  Resets `state` to `pending` so the daemon re-evaluates it.
- `DELETE /hermes/servers/{id}/skills/{skill_id}` — sets `state='removing'`,
  `enabled=false`. The row is **not deleted yet** — it disappears only after the
  daemon reports `state: "removed"` for it (see above).

## Non-goals of this contract (for now)

- No SSH access is brokered through this API — the admin's install script
  configures the box directly; sanjhubai never stores an SSH key.
- No log/metrics streaming endpoint exists yet — `hermes_agent_events` is the only
  audit trail, and it only records what `/agent/report` sends.
- No mechanism exists yet to push an urgent/out-of-band command between polls
  (e.g. "kill this skill now") — everything flows through the poll cycle above.
