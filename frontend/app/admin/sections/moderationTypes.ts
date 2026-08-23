/* Response shapes and shared label maps for the moderation review queue
 * (Phase J — owner: «اگه یه یوزر چیزای ممنوعه بیاد سرچ کنه ما باید بفهمیم»).
 *
 * Mirrors the contract frozen for this build (backend/admin_moderation.py,
 * landing alongside this file) — do not add a field here the contract does
 * not name, and do not guess at ones it left out.
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
   a colour or a Persian label. */
/** Single source for the four severities: the labels map IS the enum.
 * Hand-typed option arrays in each component drifted from it. */
export const SEVERITY_LABEL: Record<string, string> = {
  low: 'پایین', medium: 'متوسط', high: 'بالا', critical: 'بحرانی',
}

export const SEVERITY_ORDER = Object.keys(SEVERITY_LABEL)
export const SEVERITY_COLOR: Record<string, string> = {
  low: '#22c55e', medium: '#eab308', high: '#f97316', critical: '#ef4444',
}

export const DECISION_LABEL: Record<ModerationDecision, string> = {
  allow: 'مجاز', flag: 'پرچم‌گذاری', block: 'مسدود',
}
export const DECISION_BADGE: Record<ModerationDecision, string> = {
  allow: 'badge-positive', flag: 'badge-warning', block: 'badge-danger',
}

export const ACTION_LABEL: Record<ModerationUserAction, string> = {
  warn: 'هشدار', restrict: 'محدودسازی', suspend: 'تعلیق',
}
