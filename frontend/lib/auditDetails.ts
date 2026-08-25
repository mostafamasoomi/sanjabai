/* Formats the `details` column of an admin audit-log row for display.
 *
 * `audit_logs.details` is jsonb (confirmed via `\d audit_logs` against the
 * live DB), so GET /api/admin/audit-logs can hand back a string, a number,
 * a boolean, an array, a plain object, or null -- never a guaranteed
 * string. The admin panel's SecuritySection used to render it with
 * `{log.details || '—'}`, which threw React error #31 ("Objects are not
 * valid as a React child") the instant a row had a non-null object in it
 * (e.g. {"availability":"disabled"} from a model-toggle audit entry), and
 * that crash took down the whole panel via its error boundary.
 *
 * Kept in lib/ rather than inline in the component so it can be unit
 * tested without pulling in SecuritySection's '@/components/ui' and
 * '@/lib/format' imports. (vitest.config.ts now maps `@/` too, so that is no
 * longer a constraint -- but every other testable module in this codebase
 * lives here anyway, see lib/panel.ts, lib/format.tsx.)
 */

import type { Lang } from '@/components/LanguageToggle'

/** The list separator. «،» is the Persian comma; an English audit-log cell
 *  reading "a: 1، b: 2" is Persian punctuation leaking into translated text,
 *  which is exactly the kind of half-translation this pass exists to remove. */
function separator(lang: Lang): string {
  return lang === 'en' ? ', ' : '، '
}

/** Renders any jsonb-sourced value as safe, readable Persian-admin-facing
 *  text. For an object/array we want the admin to see what changed --
 *  `{"availability":"disabled"}` should read as "availability: disabled",
 *  not "[object Object]" and not an unreadable raw JSON dump. A shallow
 *  "key: value، key: value" join covers every real payload this endpoint
 *  writes today (flat key/value pairs); any nested value falls back to
 *  JSON.stringify so it still renders as text instead of crashing or
 *  silently disappearing. */
export function formatAuditDetails(details: unknown, lang: Lang = 'fa'): string {
  if (details === null || details === undefined) return '—'
  if (typeof details === 'string') return details || '—'
  if (typeof details === 'number' || typeof details === 'boolean') return String(details)
  if (Array.isArray(details)) {
    return details.length === 0 ? '—' : details.map(formatAuditDetailsValue).join(separator(lang))
  }
  if (typeof details === 'object') {
    const entries = Object.entries(details as Record<string, unknown>)
    return entries.length === 0
      ? '—'
      : entries.map(([k, v]) => `${k}: ${formatAuditDetailsValue(v)}`).join(separator(lang))
  }
  return String(details)
}

function formatAuditDetailsValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') {
    try {
      return JSON.stringify(v)
    } catch {
      return String(v)
    }
  }
  return String(v)
}
