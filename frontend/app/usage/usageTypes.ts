/* ═══════════════════════════════════════════════════════════════════════════
   Types
   Split out of page.tsx verbatim -- no behaviour change.
   ═══════════════════════════════════════════════════════════════════════════ */

export type ModelBreakdown = {
  model: string
  input_tokens: number
  output_tokens: number
  cost: number
  calls: number
}

export type UsageEvent = {
  id: number
  model: string
  input_tokens: number
  output_tokens: number
  cost: number
  created_at: string | null
}

export type UsageData = {
  current_balance: number
  total_spent_this_month: number
  total_input_tokens_this_month: number
  total_output_tokens_this_month: number
  event_count_this_month: number
  per_model_breakdown: ModelBreakdown[]
  recent_events: UsageEvent[]
}

export type ModelStat = ModelBreakdown & {
  index: number
  color: string
  name: string
  totalTokens: number
  avgTokensPerCall: number
  costPerCall: number
}
