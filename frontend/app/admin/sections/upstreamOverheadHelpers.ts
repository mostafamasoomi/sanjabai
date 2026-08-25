/* Pure, JSX-free helpers for UpstreamOverheadSection.tsx — split out on
 * purpose so they're unit-testable.
 *
 * Vitest here has no vite-react-plugin registered and tsconfig.json sets
 * `"jsx": "preserve"` (correct for Next.js, which transforms JSX itself via
 * SWC) — so Vitest's default esbuild transform cannot parse ANY `.tsx` file
 * at all, including ones that only need one non-JSX export from it. That
 * ruled out keeping this logic inside the component file (which needs JSX)
 * or having it import `faNum` from lib/format.tsx (which itself contains a
 * JSX-returning component and would hit the same wall transitively). Same
 * reasoning `app/admin/apiError.ts` was already split out for.
 *
 * `elapsedParts` deliberately returns numbers, not a Persian string — the
 * component formats those through `f.num` itself so the actual rendered
 * digits still go through the language-bound formatter (see lib/adminI18n.ts).
 *
 * This file is plain .ts, not .tsx, so it cannot call the `useLang` hook
 * (see the header note above on why Vitest can't parse .tsx at all here).
 * `parseOverheadResponse`'s error strings therefore take `lang` as a plain
 * parameter, defaulting to 'fa' so the existing unit tests — which call it
 * without a `lang` argument — keep passing unchanged. The component is the
 * one that reads `useLang()` and passes the result through.
 *
 * ── The real response contract ──────────────────────────────────────────
 * Pinned against `backend/admin_overhead.py` (both GET /admin/upstream-overhead
 * and POST /admin/upstream-overhead/measure return this same shape):
 *
 *   {
 *     "stored": {
 *       "version": 1,
 *       "measured_at": string | null,
 *       "entries": { "<upstream>:<prefix>": <overhead tokens, number> },
 *       "provider_default": { "<upstream>": <overhead tokens, number> },
 *       "measurements": {                                // absent when GET
 *         "<upstream>:<prefix>": {                        // falls back to the
 *           "overhead": number, "p1": number, "p2": number,  // never-measured
 *           "c1": number, "c2": number,                      // default (see
 *           "slope": number | null,                          // get_upstream_overhead's
 *           "sample_model": string, "measured_at": string     // `stored` fallback)
 *         }
 *       }
 *     },
 *     "storedUpdatedAt": string | null,
 *     "perProviderStats7d": [
 *       { "provider": string, "requests7d": number, "totalTokensDiscounted7d": number }
 *     ]
 *   }
 *
 * `stored.entries` is the source of truth for what a route is actually
 * charged: a value there means that "<upstream>:<prefix>" was measured
 * directly. `stored.provider_default` is a SEPARATE fallback map (smallest
 * overhead measured for that upstream this run) used at billing time for any
 * prefix that has no entry of its own — `parseOverheadResponse` keeps the two
 * as separate lists rather than merging them, so the UI can never present a
 * provider-level fallback as if it were a specific measurement (or vice
 * versa). `perProviderStats7d` is keyed by provider, not by route — several
 * route entries can share one provider's stats row, so it is returned here
 * as its own list too, never attached to a route row (that would imply a
 * per-route count that does not exist in the data and would double-count on
 * screen).
 *
 * `stored.measured_at === null` with an empty `stored.entries` is the
 * SHIPPED DEFAULT / inert state (`isInert` below) — not an error.
 *
 * ── Why this throws instead of degrading ────────────────────────────────
 * An earlier version of this file guessed at the shape (before the backend
 * contract existed) and accepted several possible envelopes/field names
 * defensively. The coordinator correctly flagged that as dangerous for this
 * specific table: silently accepting a shape the backend never actually
 * sends means a *malformed or changed* response degrades to "no data" on
 * screen, which is visually identical to "the backend legitimately has
 * nothing measured yet" (the inert default). Because this table decides
 * what every user is charged, those two situations must never look the
 * same. `parseOverheadResponse` therefore validates strictly against the
 * one real contract above and throws a descriptive Error for anything that
 * doesn't match — the component renders that as a distinct "unexpected
 * response" state, separate from both the inert-empty state and a plain
 * network failure.
 */

// Relative, not `@/components/LanguageToggle` -- see the note in
// upstreamOverheadHelpers.strings.ts on why this file avoids the `@` alias.
import type { Lang } from '@/components/LanguageToggle'
import { upstreamOverheadHelperStrings } from './upstreamOverheadHelpers.strings'

export interface OverheadRouteRow {
  /** The raw "<upstream>:<prefix>" key from `stored.entries`. */
  route_key: string
  /** `route_key` split on the first `:` — the `providers.Provider.name`. */
  provider: string
  /** `stored.entries[route_key]` — what this route is actually charged. */
  overhead_tokens: number
  /** Whether `stored.measurements[route_key]` existed to derive the fields
   *  below from. False is possible in principle (entries/measurements are
   *  always written together by the one writer today) but handled rather
   *  than assumed. */
  has_measurement: boolean
  p1: number | null
  p2: number | null
  c1: number | null
  c2: number | null
  slope: number | null
  sample_model: string | null
  measured_at: string | null
}

export interface ProviderDefaultRow {
  provider: string
  /** `stored.provider_default[provider]` — the fallback overhead applied to
   *  any prefix under this provider that has no entry of its own. */
  overhead_tokens: number
}

export interface ProviderStatRow {
  provider: string
  requests_7d: number
  tokens_discounted_7d: number
}

export interface ParsedOverhead {
  entries: OverheadRouteRow[]
  providerDefaults: ProviderDefaultRow[]
  providerStats: ProviderStatRow[]
  /** `stored.measured_at` — when a live measurement last actually ran. */
  measuredAt: string | null
  /** `storedUpdatedAt` — when the app_setting row was last written. */
  storedUpdatedAt: string | null
  /** `stored.measured_at === null && entries.length === 0` — the shipped
   *  default. Distinct from a parse failure: this is a valid, expected
   *  response, just one that says nothing has been measured yet. */
  isInert: boolean
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function fail(message: string): never {
  throw new Error(message)
}

/** Strictly validates and flattens the real `/admin/upstream-overhead`
 *  response (see the contract doc above). Throws rather than guessing on
 *  anything that doesn't match — see "Why this throws" above.
 *
 *  `lang` is a plain parameter, not `useLang()`, because this is not a
 *  component — see the header comment. Defaults to 'fa' so the existing
 *  unit tests, which call this without a `lang` argument, keep passing. */
export function parseOverheadResponse(raw: unknown, lang: Lang = 'fa'): ParsedOverhead {
  const s = upstreamOverheadHelperStrings(lang)

  if (!isPlainObject(raw)) fail(s.notObject)

  const stored = raw.stored
  if (!isPlainObject(stored)) fail(s.missingStored)

  const entriesRaw = stored.entries
  if (!isPlainObject(entriesRaw)) fail(s.entriesNotMap)

  const providerDefaultRaw = stored.provider_default
  if (!isPlainObject(providerDefaultRaw)) fail(s.providerDefaultNotMap)

  // Absent entirely on the never-measured default (see get_upstream_overhead's
  // fallback dict, which omits it) — treated as "no derivation data", not an error.
  const measurementsRaw = isPlainObject(stored.measurements) ? stored.measurements : {}

  const entries: OverheadRouteRow[] = Object.entries(entriesRaw).map(([routeKey, overheadValue]) => {
    if (typeof overheadValue !== 'number' || !Number.isFinite(overheadValue)) {
      fail(s.invalidOverheadForRoute(routeKey))
    }
    const measurement = isPlainObject(measurementsRaw[routeKey]) ? measurementsRaw[routeKey] : null
    const numOrNull = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
    const strOrNull = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v : null)
    return {
      route_key: routeKey,
      provider: routeKey.includes(':') ? routeKey.split(':', 1)[0] : routeKey,
      overhead_tokens: overheadValue,
      has_measurement: measurement != null,
      p1: measurement ? numOrNull(measurement.p1) : null,
      p2: measurement ? numOrNull(measurement.p2) : null,
      c1: measurement ? numOrNull(measurement.c1) : null,
      c2: measurement ? numOrNull(measurement.c2) : null,
      // slope can legitimately be null (c1 == c2 guard in admin_overhead.py).
      slope: measurement ? numOrNull(measurement.slope) : null,
      sample_model: measurement ? strOrNull(measurement.sample_model) : null,
      measured_at: measurement ? strOrNull(measurement.measured_at) : null,
    }
  })

  const providerDefaults: ProviderDefaultRow[] = Object.entries(providerDefaultRaw).map(([provider, overheadValue]) => {
    if (typeof overheadValue !== 'number' || !Number.isFinite(overheadValue)) {
      fail(s.invalidDefaultForProvider(provider))
    }
    return { provider, overhead_tokens: overheadValue }
  })

  const statsRaw = raw.perProviderStats7d
  const providerStats: ProviderStatRow[] = Array.isArray(statsRaw)
    ? statsRaw.filter(isPlainObject).map((s) => ({
        provider: typeof s.provider === 'string' ? s.provider : '—',
        requests_7d: typeof s.requests7d === 'number' && Number.isFinite(s.requests7d) ? s.requests7d : 0,
        tokens_discounted_7d:
          typeof s.totalTokensDiscounted7d === 'number' && Number.isFinite(s.totalTokensDiscounted7d)
            ? s.totalTokensDiscounted7d
            : 0,
      }))
    : []

  const measuredAt = typeof stored.measured_at === 'string' ? stored.measured_at : null
  const storedUpdatedAt = typeof raw.storedUpdatedAt === 'string' ? raw.storedUpdatedAt : null

  return {
    entries,
    providerDefaults,
    providerStats,
    measuredAt,
    storedUpdatedAt,
    isInert: entries.length === 0 && measuredAt === null,
  }
}

/** Minutes/seconds breakdown of an elapsed duration, clamped at zero.
 *  `60_000` -> `{ minutes: 1, seconds: 0 }`, never a stray "0 seconds". */
export function elapsedParts(ms: number): { minutes: number; seconds: number } {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  return { minutes: Math.floor(totalSeconds / 60), seconds: totalSeconds % 60 }
}
