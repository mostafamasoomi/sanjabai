/* ═══════════════════════════════════════════════════════════════════════════
   Types and pure helpers shared by PackagesSection.tsx and the components it
   was split into (PackagesRow.tsx, PackagesCreateForm.tsx,
   PackagesPremiumThreshold.tsx) to stay under the 500-line-per-file cap.
   No JSX here on purpose -- keeps this file tiny and easy to reuse.

   `rate_limit_per_window` / `premium_rate_limit_per_window` are migration
   0046's two new columns: pure per-5-hour-window rate limits, unrelated to
   the `request_quota`/`token_quota` pair that creates a wallet-bypassing
   `package_entitlement` (see admin_packages.py's `_RATE_LIMIT_FIELDS`
   comment). `premium_rate_limit_per_window` is a SUBSET counted from inside
   `rate_limit_per_window`, never an additional cap on top of it.
   ═══════════════════════════════════════════════════════════════════════════ */

export interface PackageRow {
  id: string
  name_fa: string | null
  name_en: string | null
  description: string | null
  active: boolean
  base_amount: number | null
  total_credits: number | null
  bonus_percent: number | null
  request_quota: number | null
  token_quota: number | null
  validity_days: number | null
  max_cost_per_request_toman: number | null
  rate_limit_per_window: number | null
  premium_rate_limit_per_window: number | null
  price: number
  credits: number
  bonus_credits: number
  name: string
  sort_order: number
}

export interface PackagesSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

export type Draft = {
  name_fa: string
  name_en: string
  description: string
  active: boolean
  base_amount: string
  total_credits: string
  bonus_percent: string
  request_quota: string
  token_quota: string
  validity_days: string
  max_cost_per_request_toman: string
  rate_limit_per_window: string
  premium_rate_limit_per_window: string
  price: string
  credits: string
  bonus_credits: string
}

export function toDraft(p: PackageRow): Draft {
  const s = (v: number | null) => (v == null ? '' : String(v))
  return {
    name_fa: p.name_fa ?? '', name_en: p.name_en ?? '', description: p.description ?? '',
    active: p.active,
    base_amount: s(p.base_amount), total_credits: s(p.total_credits), bonus_percent: s(p.bonus_percent),
    request_quota: s(p.request_quota), token_quota: s(p.token_quota), validity_days: s(p.validity_days),
    max_cost_per_request_toman: s(p.max_cost_per_request_toman),
    rate_limit_per_window: s(p.rate_limit_per_window),
    premium_rate_limit_per_window: s(p.premium_rate_limit_per_window),
    price: s(p.price), credits: s(p.credits), bonus_credits: s(p.bonus_credits),
  }
}

/** true when a quota is set (draft) with no ceiling -- the loss path the
    backend rejects; mirrored here so the warning shows before a failed save.
    Takes only the three fields it needs so it also works for the create
    form's draft, which doesn't carry every `Draft` field.

    Deliberately unrelated to `rate_limit_per_window`/
    `premium_rate_limit_per_window` -- those never create a wallet-bypassing
    entitlement, so they carry no loss path and no ceiling requirement (see
    admin_packages.py's `_check_loss_path` docstring). */
export function isLossPath(d: { request_quota: string; token_quota: string; max_cost_per_request_toman: string }): boolean {
  const hasQuota = d.request_quota.trim() !== '' || d.token_quota.trim() !== ''
  return hasQuota && d.max_cost_per_request_toman.trim() === ''
}

export type NewPackageDraft = {
  id: string; name_fa: string; name_en: string
  base_amount: string; total_credits: string; bonus_percent: string
  request_quota: string; token_quota: string; max_cost_per_request_toman: string
  rate_limit_per_window: string; premium_rate_limit_per_window: string
  validity_days: string; active: boolean
}

export const EMPTY_NEW_PACKAGE: NewPackageDraft = {
  id: '', name_fa: '', name_en: '',
  base_amount: '', total_credits: '', bonus_percent: '',
  request_quota: '', token_quota: '', max_cost_per_request_toman: '',
  rate_limit_per_window: '', premium_rate_limit_per_window: '',
  validity_days: '', active: true,
}
