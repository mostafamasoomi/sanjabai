/* Pure, JSX-free helpers for RouterProbeSection.tsx — split out on purpose so
 * they're unit-testable, exactly the same reason upstreamOverheadHelpers.ts
 * was split out of UpstreamOverheadSection.tsx (see that file's header):
 * this repo's vitest has no jsdom, so a component's JSX is untestable and its
 * display-decision logic must not live inside it.
 *
 * NOTE on the packet's exclusive file set: P-ADMIN listed only
 * RouterProbeSection.tsx / .strings.ts / routerProbe.test.ts, but its own body
 * says "Pure display logic goes in a helpers module... exactly as
 * upstreamOverheadHelpers.ts does" — that idiom file is a *sibling* of
 * UpstreamOverheadSection.tsx, not a shared/senior-owned file, so this file is
 * added to satisfy that explicit instruction. Flagged in the handoff report.
 *
 * ── The real response contract ──────────────────────────────────────────
 * Pinned against `backend/admin_smart_router.py` + `backend/services/
 * router_probe.py` (read directly, not guessed):
 *
 *   GET /admin/smart-router/probe ->
 *     { stored: { version, measured_at: string|null,
 *                 results: { "<public_id>": <entry> } },
 *       storedUpdatedAt: string|null }
 *
 *   POST /admin/smart-router/probe (runs the live measurement) ->
 *     { status: 'ok', measured: number, eligible: number,
 *       value: <same shape as GET's `stored`> }
 *
 * `results` is keyed by `Candidate.public_id` — router_probe.py's module
 * docstring is explicit that this key is a public_id, never a provider or
 * upstream name, and this file must never invent one either (see
 * "no provider leak" below).
 *
 * One entry (services/router_probe.py `_probe_one` / `_merge_transient`):
 *   { ok: boolean,
 *     reason?: string,        // present when ok===false, or when a LATER
 *                              // transient recheck overwrote it on a row
 *                              // that is still ok===true (see below)
 *     at?: string,             // ISO, when this entry was last written
 *     retry_after?: string,    // ISO, only meaningful on a transient reason
 *     shape_ok?: boolean, discriminates?: boolean,
 *     sample_reply?: string,   // bad_shape diagnostic — OUR probe's own
 *                              // reply capture, never a provider field
 *     samples?: Record<'greeting'|'code'|'reasoning', number|null> }
 *
 * ── The three outcomes, and the one easy-to-get-wrong wrinkle ─────────────
 * router_probe.py's `_merge_transient`: a transient failure on a model that
 * ALREADY had `ok: true` from a previous successful measurement does NOT
 * flip it to false — it keeps `ok: true` verbatim and just stamps `reason`/
 * `retry_after` with the transient info as a diagnostic. So classification
 * here checks `ok` FIRST, unconditionally: `ok === true` is always
 * `'eligible'`, even if a leftover transient `reason` string is still
 * sitting on the row from the most recent recheck. Only when `ok !== true`
 * does the `reason` string decide permanent vs transient. Collapsing this
 * would either flatten a real transient/permanent distinction (the specific
 * mistake the packet calls out) or — worse — misreport an already-proven
 * router model as merely "not eligible yet" because of a later flaky probe.
 */

export type RouterProbeState = 'eligible' | 'ineligiblePermanent' | 'ineligibleTransient'

export interface RouterProbeRow {
  /** The `results` map key — a `Candidate.public_id`. Never a provider or
   *  upstream name; see the contract note above. */
  publicId: string
  state: RouterProbeState
  /** Raw `reason` string from the stored entry (e.g. `bad_shape`,
   *  `no_discrimination`, `transient_http_429`) — presentation maps this to
   *  a human label; kept raw here so nothing here has to guess at every
   *  possible reason string the backend might ever emit. */
  reason: string | null
  /** Only meaningful when `state === 'ineligibleTransient'`. */
  retryAfter: string | null
  /** When this entry was last written. */
  at: string | null
  /** `bad_shape` diagnostic — the probe's own captured reply, never a
   *  provider/upstream field. */
  sampleReply: string | null
}

export interface ParsedRouterProbe {
  /** `stored.measured_at` — when the scan that produced this snapshot ran.
   *  Global to the whole scan, not per-model (see router_probe.py: rows not
   *  re-scanned this round keep their OLD `at`, but the top-level
   *  `measured_at` always advances to "now" — matching `router_eligibility`'s
   *  own staleness check, which reads this same field). */
  measuredAt: string | null
  /** `storedUpdatedAt` — when the app_setting row was last written. */
  storedUpdatedAt: string | null
  rows: RouterProbeRow[]
  /** True when the probe has never been run at all (missing/empty stored
   *  value) — distinct from "it ran and every model failed", which has
   *  `rows.length > 0`. See the packet: a missing/empty stored value must
   *  render an honest "never measured" state, not an empty table that reads
   *  as "all models failed". */
  neverMeasured: boolean
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function strOrNull(v: unknown): string | null {
  return typeof v === 'string' && v.trim() ? v : null
}

/** One stored entry -> its display state. `ok === true` wins unconditionally
 *  — see the "one easy-to-get-wrong wrinkle" note above the module's export
 *  section. Anything else is permanent unless its `reason` carries the
 *  `transient_` prefix `_merge_transient` always uses. */
function classifyEntry(entry: Record<string, unknown>): RouterProbeState {
  if (entry.ok === true) return 'eligible'
  const reason = strOrNull(entry.reason)
  if (reason && reason.startsWith('transient_')) return 'ineligibleTransient'
  return 'ineligiblePermanent'
}

/** Strictly-tolerant flatten of the real `/admin/smart-router/probe`
 *  response (see the contract doc above). Deliberately never throws, unlike
 *  parseOverheadResponse's sibling in upstreamOverheadHelpers.ts: this table
 *  has no "table decides what a user is charged" stake that demands failing
 *  loudly on a shape drift, and the packet explicitly requires a malformed
 *  payload to degrade quietly rather than crash the section. A row for a
 *  malformed individual entry is simply skipped rather than fabricated. */
export function parseRouterProbeResponse(raw: unknown): ParsedRouterProbe {
  const empty: ParsedRouterProbe = { measuredAt: null, storedUpdatedAt: null, rows: [], neverMeasured: true }
  if (!isPlainObject(raw)) return empty

  const stored = raw.stored
  if (!isPlainObject(stored)) return empty

  const resultsRaw = isPlainObject(stored.results) ? stored.results : {}
  const rows: RouterProbeRow[] = []
  for (const [publicId, entryRaw] of Object.entries(resultsRaw)) {
    if (!isPlainObject(entryRaw)) continue // malformed row: skipped, not fabricated
    rows.push({
      publicId,
      state: classifyEntry(entryRaw),
      reason: strOrNull(entryRaw.reason),
      retryAfter: strOrNull(entryRaw.retry_after),
      at: strOrNull(entryRaw.at),
      sampleReply: strOrNull(entryRaw.sample_reply),
    })
  }

  const measuredAt = strOrNull(stored.measured_at)
  const storedUpdatedAt = strOrNull(raw.storedUpdatedAt)

  return {
    measuredAt,
    storedUpdatedAt,
    rows,
    neverMeasured: rows.length === 0 && measuredAt === null,
  }
}

/** A result older than STALE_AFTER (7 days, mirroring services/router_probe.py's
 *  identical constant) is still ACCEPTED — `_router_model` honours it — but an
 *  admin looking at this page deserves to know they are acting on old
 *  information. Missing/unparsable counts as stale, matching the backend's
 *  own `_is_stale`: the safe direction for "should I warn" is to warn.
 *
 *  `now` is a parameter (defaulting to the real clock) purely so the 7-day
 *  boundary can be tested deterministically on both sides without faking
 *  global time. */
const STALE_AFTER_MS = 7 * 24 * 60 * 60 * 1000

export function isProbeStale(measuredAt: string | null, now: Date = new Date()): boolean {
  if (!measuredAt) return true
  const t = new Date(measuredAt).getTime()
  if (Number.isNaN(t)) return true
  // Strictly greater-than, matching services/router_probe.py `_is_stale`:
  // exactly 7 days old is not yet stale.
  return now.getTime() - t > STALE_AFTER_MS
}
