'use client'

import type { HealthStatus, ModelCatalogItem, ModelHealth } from '@/types/catalog'
import type { Lang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { modelUtilsStrings } from './modelUtils.strings'

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

/** Persian default, kept as a plain Record (not a `(lang) => …` reader) for
 *  callers written before this file went bilingual — app/status/page.tsx
 *  (owned by another agent) still does `HEALTH_LABEL[status]` directly. Do
 *  not remove without updating that file too. New code should call
 *  `healthLabel(lang)` instead. */
export const HEALTH_LABEL: Record<HealthStatus, string> = modelUtilsStrings('fa').health

/** Bilingual reader — use this in any newly-translated component. */
export function healthLabel(lang: Lang): Record<HealthStatus, string> {
  return modelUtilsStrings(lang).health
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

export function formatPriceIRT(price: number, lang: Lang = 'fa'): string {
  if (price == null || isNaN(price)) return '—'
  const n = fmt(lang).num(price)
  return `${n} ${modelUtilsStrings(lang).priceUnit}`
}

export function formatContextWindow(ctx: number): string {
  if (!ctx || isNaN(ctx)) return '—'
  if (ctx >= 1_000_000) return `${(ctx / 1_000_000).toFixed(ctx % 1_000_000 === 0 ? 0 : 1)}M`
  if (ctx >= 1000) return `${Math.round(ctx / 1000)}K`
  return `${ctx}`
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
