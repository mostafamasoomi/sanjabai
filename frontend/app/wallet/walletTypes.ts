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

export type PaymentBannerState = { ok: boolean; text: string } | null
