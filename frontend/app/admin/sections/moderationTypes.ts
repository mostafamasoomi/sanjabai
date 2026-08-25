import type { Lang } from '@/components/LanguageToggle'
import { moderationTypesStrings } from './moderationTypes.strings'

/* Response shapes and shared label maps for the moderation review queue
 * (Phase J — owner: «اگه یه یوزر چیزای ممنوعه بیاد سرچ کنه ما باید بفهمیم»).
 *
 * Mirrors the contract frozen for this build (backend/admin_moderation.py,
 * landing alongside this file) — do not add a field here the contract does
 * not name, and do not guess at ones it left out.
 *
 * Not a component, so no `useLang()` here. Every label helper below takes
 * `lang` as a parameter and must be called from a component that already
 * resolved it via `useLang()`.
 */

export type ModerationDecision = 'allow' | 'flag' | 'block'

// GET /admin/moderation/events?page&limit&severity&decision&q
// Only `snippet` is ever shown to an admin here — never the full message.
export interface ModerationEvent {
  id: number
  user_id: number
  user_email: string
  conversation_id: number | string
  category: string
  severity: string
  rule_id: number | null
  snippet: string
  decision: ModerationDecision
  created_at: string
}

export interface ModerationEventsPayload {
  items: ModerationEvent[]
  total: number
  page: number
  limit: number
}

// GET /admin/moderation/rules ; POST create ; POST /{id} update ; DELETE /{id}
export interface ModerationRule {
  id: number
  pattern: string
  category: string
  severity: string
  enabled: boolean
  notes: string
  updated_at: string
}

// GET /admin/moderation/users/{uid}
export interface ModerationUserRisk {
  risk_score: number
  event_count: number
  recent: ModerationEvent[]
}

// POST /admin/moderation/users/{uid}/action  { action, reason }
export type ModerationUserAction = 'warn' | 'restrict' | 'suspend'

/* Severity has no enum in the contract (it's a free-text column filtered by
   substring). These four are the values the backend agent confirmed it
   writes; an unrecognised value still renders fine everywhere — every call
   site falls back to the raw string via `?? severity` — it just won't carry
   a colour or a Persian/English label. */

/** The four severities in display order — the FA side of the dictionary IS
 *  the enum. Hand-typed option arrays in each component drifted from it, so
 *  this is the single source; language-independent since it only reads
 *  keys (always resolved against 'fa', which carries every key). */
export const SEVERITY_ORDER = Object.keys(moderationTypesStrings('fa').severity)

export const SEVERITY_COLOR: Record<string, string> = {
  low: '#22c55e', medium: '#eab308', high: '#f97316', critical: '#ef4444',
}

/** Severity label for a language, falling back to the raw value for an
 *  unrecognised severity — same fallback every call site relied on before. */
export function severityLabel(severity: string, lang: Lang): string {
  return moderationTypesStrings(lang).severity[severity] ?? severity
}

export const DECISION_BADGE: Record<ModerationDecision, string> = {
  allow: 'badge-positive', flag: 'badge-warning', block: 'badge-danger',
}

/** Decision label for a language, falling back to the raw value — same
 *  fallback every call site relied on before. */
export function decisionLabel(decision: ModerationDecision | string, lang: Lang): string {
  return moderationTypesStrings(lang).decision[decision] ?? decision
}

export function actionLabel(action: ModerationUserAction, lang: Lang): string {
  return moderationTypesStrings(lang).action[action]
}
