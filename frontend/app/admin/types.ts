/* Response shapes for the admin panel.
 *
 * Moved out of AdminPanel.tsx when the shell was thinned down; AdminPanel.tsx
 * re-exports every name here so the sections that import them from
 * '../AdminPanel' keep compiling.
 *
 * Each type mirrors what the backend actually returns, verified against the
 * route rather than assumed — see the per-type notes.
 */

export interface Analytics {
  user_count: number
  active_users: number
  total_revenue: number
  total_tokens: number
  conv_count: number
  recent_ledger: { id: number; user_id: number; amount: number; reason: string; created_at: string }[]
}

export interface PricingRow {
  model: string
  input_per_million: number
  output_per_million: number
  currency: string
  availability?: string
}

export interface ModelTestResult {
  ok: boolean
  latency_ms: number
  error: string | null
  upstream?: string
}

// GET /admin/credit-packages (backend/admin_plans.py). Amounts are integer
// toman like every other money figure in this codebase — never rial, and
// never scaled on the way in or out.
export interface CreditPackageRow {
  id: string
  name_fa: string
  name_en: string
  base_amount: number
  bonus_percent: number
  total_credits: number
  model_id: string | null
  active: boolean
  sort_order: number
}

export interface FeatureRow {
  id: number
  title: string
  description: string
  icon: string
  order_idx: number
  active: boolean
}

export interface DiscountRow {
  id: number
  code: string
  percent: number
  active: boolean
}

export interface ProxyConfig {
  proxy_type: string
  proxy_url: string
  active: boolean
}

export interface SecurityStats {
  threat_level: 'low' | 'medium' | 'high' | 'critical'
  failed_logins_24h: number
  active_sessions: number
  failed_login_chart: { hour: string; count: number }[]
  banned_users: { id: number; email: string; username: string; banned_at: string }[]
}

// No endpoint feeds this today. The security screen used to render an
// always-empty "رویدادهای امنیتی" table from it, which read as "nothing
// suspicious has happened" when the truth was "nothing is being collected";
// that table is gone. The type stays exported because it is part of this
// module's public surface and a real feed is still the intent.
export interface SecurityEvent {
  id: number
  event_type: string
  user_id: number | null
  user_email: string | null
  ip_address: string | null
  details: string | null
  created_at: string
}

// GET /admin/audit-logs -> { logs, total, page, limit } (admin_analytics.py).
// The column is `admin_user_id`; this type previously declared `admin_id`,
// a name the server has never sent.
export interface AuditLog {
  id: number
  admin_user_id: number | null
  action: string
  target_type: string | null
  target_id: number | null
  details: string | null
  ip_address: string | null
  user_agent: string | null
  created_at: string
}

// Mirrors exactly what GET /admin/users returns, verified against the live
// endpoint rather than assumed.
//
// This type previously declared `username`, `is_active`, `plan` and
// `wallet_balance` -- four fields the server has never sent. TypeScript was
// satisfied because the rows arrive as untyped JSON and get asserted into
// this shape, so the mismatch could not surface at compile time; those
// columns simply rendered blank in production, and the status badge read
// "inactive" for every user because `is_active` was always undefined.
//
// There is no `role` column on `users` either -- the only role signal is
// `preferences.panel` (consumer/developer), which the user detail drawer
// reads. And there is no editable `plan` on a user row; a plan is expressed
// through the `subscriptions` table, not a column here.
//
// `balance` is the authoritative wallet balance; `ledger_sum` is the same
// figure reconstructed from the append-only ledger. They must be equal --
// a divergence is a billing-integrity bug, which is why both are shown.
export interface UserRow {
  id: number
  email: string
  phone: string | null
  telegram_id: number | null
  referral_code: string | null
  referred_by: number | null
  created_at: string
  banned: boolean
  balance: number
  reserved: number
  ledger_sum: number
  used_today: number
}

export interface UserDetail {
  user: {
    id: number; email: string; phone: string; telegram_id: number;
    display_name: string; bio: string; avatar_url: string;
    timezone: string; language: string; banned: boolean;
    created_at: string; preferences: Record<string, unknown>;
  }
  balance: number
  wallet: { balance: number; reserved: number }
  quota: { daily_limit: number; used_today: number; reset_at: string } | null
  stats: {
    conversation_count: number; total_tokens: number;
    usage_events: number; total_cost: number;
    payment_count: number; total_payments: number;
  }
}

export type UserDetailTab = 'overview' | 'conversations' | 'usage' | 'ledger' | 'payments'
