'use client'

// Single source of truth — synced with backend _WORKING_SET (2026-07-16 live test)
export const WORKING_MODEL_IDS = [
  'tencent-hy3',
  'mistral-large',
  'mistral-medium-3-5',
  'deepseek-v4-pro',
  'deepseek-v4-flash-bynara',
  'deepseek-v4-pro-bynara',
  'mimo-v2.5-pro',
  'mimo-v2.5-pro-ultraspeed',
] as const

const WORKING_SET = new Set<string>(WORKING_MODEL_IDS.map(s => s.toLowerCase()))

export function isWorkingModel(id: string): boolean {
  if (!id) return false
  const nid = id.toLowerCase()
  if (WORKING_SET.has(nid)) return true
  // fuzzy: check includes core token for bynara models
  return (
    nid.includes('tencent-hy3') ||
    nid.includes('mistral-large') ||
    nid.includes('mistral-medium') ||
    nid.includes('deepseek-v4') ||
    nid.includes('mimo-v2.5-pro')
  )
}

export function getModelIcon(capabilities: string[] = [], recommendedFor: string[] = []): string {
  const caps = (capabilities || []).map(c => c.toLowerCase())
  const rec = (recommendedFor || []).map(r => r.toLowerCase())
  const all = [...caps, ...rec].join(' ')

  if (all.includes('code') || all.includes('coding') || all.includes('developer')) return '💻'
  if (all.includes('reason') || all.includes('thinking') || all.includes('analysis')) return '🔬'
  if (all.includes('vision') || all.includes('image') || all.includes('multimodal')) return '👁️'
  if (all.includes('fast') || all.includes('flash') || all.includes('turbo')) return '⚡'
  if (all.includes('chat') || all.includes('general') || all.includes('common')) return '🧠'
  return '🤖'
}

export function formatPriceIRT(price: number): string {
  if (price == null || isNaN(price)) return '—'
  // Price expected already in Toman (IRT). Show fa-IR formatting
  try {
    return `${Number(price).toLocaleString('fa-IR')} تومان/۱M`
  } catch {
    return `${price} تومان/۱M`
  }
}

export function formatPricePair(
  input: number | undefined,
  output: number | undefined
): { input: string; output: string } {
  return {
    input: input != null ? formatPriceIRT(input) : '—',
    output: output != null ? formatPriceIRT(output) : '—',
  }
}

export function formatContextWindow(ctx: number): string {
  if (!ctx || isNaN(ctx)) return '—'
  if (ctx >= 1_000_000) return `${(ctx / 1_000_000).toFixed(ctx % 1_000_000 === 0 ? 0 : 1)}M`
  if (ctx >= 1000) return `${Math.round(ctx / 1000)}K`
  return `${ctx}`
}

export function getProviderLabel(provider: string): string {
  if (!provider) return 'نامشخص'
  const p = provider.toLowerCase()
  const map: Record<string, string> = {
    bynara: 'Bynara',
    mistral: 'Mistral',
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    google: 'Google',
    tencent: 'Tencent',
    kimi: 'Kimi',
    moonshot: 'Moonshot',
    agnes: 'Agnes',
    xai: 'xAI',
    mimo: 'Mimo',
  }
  return map[p] ?? provider
}

export function isRecommendedModel(m: {
  id: string
  recommendedFor?: string[]
  capabilities?: string[]
}): boolean {
  const rec = (m.recommendedFor || []).map(s => s.toLowerCase())
  if (rec.includes('common') || rec.includes('general') || rec.includes('recommended')) return true
  if (isWorkingModel(m.id)) return true
  if ((m.capabilities?.length ?? 0) > 1) return true
  return false
}
