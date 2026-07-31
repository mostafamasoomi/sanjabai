'use client'

import type { HealthStatus, ModelCatalogItem, ModelHealth } from '@/types/catalog'
import { faNum } from '@/lib/format'

/* ═══════════════════════════════════════════════════════════════════════════
   Model health

   This file used to export a hard-coded WORKING_MODEL_IDS array, described in
   its own comment as "synced with backend _WORKING_SET (2026-07-16 live
   test)" — a snapshot of one afternoon's manual testing that nothing kept up
   to date, plus a fuzzy substring match that guessed at anything not on the
   list.

   Health now comes from the backend, which measures it continuously from
   synthetic probes and the outcomes of real requests. These helpers only
   interpret what the API reports.
   ═══════════════════════════════════════════════════════════════════════════ */

/** Health of a catalog entry, defaulting to unknown on an older backend. */
export function healthOf(m: Pick<ModelCatalogItem, 'health'>): ModelHealth {
  return (
    m.health ?? {
      status: 'unknown',
      successRate: null,
      latencyP50Ms: null,
      latencyP95Ms: null,
      sampleCount: 0,
      lastOkAt: null,
      lastError: null,
      checkedAt: null,
    }
  )
}

/**
 * Is this model worth offering to a user?
 *
 * `unknown` counts as usable — it means nobody has exercised the model
 * recently, not that it is broken. Excluding it would empty the picker on a
 * fresh deployment, before the first probe sweep has run.
 */
export function isUsableModel(m: Pick<ModelCatalogItem, 'health'>): boolean {
  return healthOf(m).status !== 'down'
}

/** True only when the model is actively answering. */
export function isHealthyModel(m: Pick<ModelCatalogItem, 'health'>): boolean {
  return healthOf(m).status === 'healthy'
}

export const HEALTH_LABEL: Record<HealthStatus, string> = {
  healthy: 'سالم',
  degraded: 'ناپایدار',
  down: 'در دسترس نیست',
  unknown: 'نامشخص',
}

/** Maps to the semantic colour tokens in globals.css. */
export const HEALTH_TONE: Record<HealthStatus, string> = {
  healthy: 'var(--positive)',
  degraded: 'var(--warning)',
  down: 'var(--danger)',
  unknown: 'var(--text-dim)',
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
  // Price is already in tomans. The unit used to read "تومان/۱M": a Persian
  // word, a slash, then a Latin M, which the RTL run reorders. Spelled out in
  // Persian it is unambiguous.
  return `${faNum(price)} تومان/میلیون`
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
  health?: ModelHealth
}): boolean {
  const rec = (m.recommendedFor || []).map(s => s.toLowerCase())
  if (rec.includes('common') || rec.includes('general') || rec.includes('recommended')) return true
  // A model that is measurably answering right now is worth recommending.
  if (m.health?.status === 'healthy') return true
  if ((m.capabilities?.length ?? 0) > 1) return true
  return false
}
