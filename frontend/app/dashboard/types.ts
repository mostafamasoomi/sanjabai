/* ═══════════════════════════════════════════════════════════════════════════
   Shared types and constants for the dashboard page.
   Split out of page.tsx to keep every file under the project's 500-line cap.
   ═══════════════════════════════════════════════════════════════════════════ */

export type UserProfile = {
  id: number
  email: string
  username?: string
  phone?: string
  plan: string
  is_active: boolean
  created_at: string
}

export type Usage = {
  total_spent_this_month: number
  // The count of billable calls this month, as returned by /me/usage
  // (backend/admin_usage_me.py). This is the field the "تعداد مکالمات" card
  // actually renders -- it used to be reached through `as any` because the
  // type declared a `turns` field the endpoint never sends.
  event_count_this_month: number
  total_input_tokens_this_month: number
}

export type LedgerEntry = {
  id: number
  amount: number
  balance_after: number
  reason: string
  created_at: string
}

export type ModelItem = { id: string }

export type Subscription = {
  id: number
  user_id: number
  plan: string
  starts_at: string
  ends_at: string
  status: string
  monthly_token_quota: number
  tokens_used_this_period: number
  auto_renew: boolean
  price_paid: number
} | null

export type SubscriptionPlan = {
  id: number
  name_fa: string
  name_en: string
  price_monthly: number
  monthly_token_quota: number
  daily_token_limit: number
  features: string[]
} | null

export type BillingSettings = {
  user_id: number
  payg_enabled: boolean
  payg_hard_limit: number | null
  notify_on_usage_pct: number
} | null

/* Numerals, dates and money all come from lib/format — see the note there on
   why this page no longer calls toLocaleString directly. */

export const planLabels: Record<string, string> = {
  free: 'رایگان',
  pro: 'حرفه‌ای',
  enterprise: 'سازمانی',
}

export const planBadgeClass: Record<string, string> = {
  free: 'badge',
  pro: 'badge badge-accent',
  enterprise: 'badge badge-positive',
}
