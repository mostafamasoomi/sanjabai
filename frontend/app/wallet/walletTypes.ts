export type LedgerEntry = {
  id: number
  amount: number
  balance_after: number
  reason: string
  created_at: string
}

export type PaymentRecord = {
  id: number
  amount: number
  status: string
  created_at: string
}

export type CreditPackage = {
  id: string
  name_fa: string
  name_en: string
  base_amount: number
  bonus_percent: number
  total_credits: number
  model_id: string | null
}

export type LedgerFilter = 'all' | 'credit' | 'debit'

// `kind` rather than a pre-rendered string, so the banner's text is looked
// up in the current UI language at render time (PaymentBanner.tsx) instead
// of being frozen in whatever language was active the moment the gateway
// redirect landed.
export type PaymentBannerState = { ok: boolean; kind: 'success' | 'failed' | 'error' } | null
