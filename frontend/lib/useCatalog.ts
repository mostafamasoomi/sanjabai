'use client'

import { useEffect, useState } from 'react'
import { type ModelCatalogItem, type CatalogResponse } from '@/types/catalog'

export type UseCatalogState = {
  models: ModelCatalogItem[]
  loading: boolean
  error: boolean
  source: string
}

/* ── Module-level cache to deduplicate concurrent requests ─────────── */
let cachedPromise: Promise<CatalogResponse> | null = null
let cachedData: CatalogResponse | null = null
const CACHE_TTL_MS = 60_000 // 60 seconds
let cacheTimestamp = 0

function fetchCatalog(): Promise<CatalogResponse> {
  // Return cached data if still fresh
  if (cachedData && Date.now() - cacheTimestamp < CACHE_TTL_MS) {
    return Promise.resolve(cachedData)
  }
  // Reuse in-flight promise if one exists
  if (cachedPromise) return cachedPromise

  cachedPromise = fetch('/api/catalog/models')
    .then((res) => res.json())
    .then((data: CatalogResponse) => {
      cachedData = data
      cacheTimestamp = Date.now()
      cachedPromise = null
      return data
    })
    .catch((err) => {
      cachedPromise = null // allow retry on failure
      throw err
    })

  return cachedPromise
}

/* ── Price band ──────────────────────────────────────────────────────
   The catalog used to expose `provider` (an internal routing id such as
   "bynara" or "freellmapi-s2") for grouping and filtering in the UI. Users
   must never see which upstream serves a model — only admins do — so the
   field is gone from the public contract. Wherever the UI grouped, filtered,
   or badged by provider, it now uses a price band computed from the one
   field that varies meaningfully and is honestly user-facing:
   `pricing.inputPerMillion`.

   The split is relative to whatever model list is on screen, not a fixed
   currency threshold, so it stays sensible as prices move. */
export type PriceBand = 'free' | 'standard' | 'premium'

export const PRICE_BAND_LABEL: Record<PriceBand, string> = {
  free: 'رایگان',
  standard: 'استاندارد',
  premium: 'حرفه‌ای',
}

export const PRICE_BAND_ORDER: PriceBand[] = ['free', 'standard', 'premium']

/**
 * Buckets a model into a coarse price tier relative to `allModels` (usually
 * the currently visible/filtered list). Free (no per-token input cost) is
 * its own band; paid models split at the median paid price into "standard"
 * and "premium".
 */
export function priceBand(
  model: Pick<ModelCatalogItem, 'pricing'>,
  allModels: Pick<ModelCatalogItem, 'pricing'>[],
): PriceBand {
  const price = model.pricing?.inputPerMillion ?? 0
  if (price <= 0) return 'free'
  const paid = allModels
    .map((m) => m.pricing?.inputPerMillion ?? 0)
    .filter((p) => p > 0)
    .sort((a, b) => a - b)
  if (paid.length === 0) return 'standard'
  const median = paid[Math.floor(paid.length / 2)]
  return price <= median ? 'standard' : 'premium'
}

/* ── Context-window band ─────────────────────────────────────────────
   `capabilities` and `recommendedFor` are `[]` on every row in the catalog
   today (checked directly against model_catalog: 0/1134 rows have either
   populated), so a filter built on them would render a control with nothing
   to select. `modalities` is populated, but identically on every single row
   — `{"input":["text"],"output":["text"]}` for all 1134 — so a filter there
   would offer exactly one option that never actually excludes anything,
   which is the same "broken control" problem in a different shape. Neither
   ships.

   `contextWindow`, by contrast, has real spread across the full catalog (13
   distinct values from 8,192 to 1,050,000, clustered well apart), so it is
   bucketed the same way price is: a small fixed set of bands relative to the
   whole catalog rather than one chip per exact number. */
export type ContextBand = 'small' | 'medium' | 'large' | 'xlarge'

export const CONTEXT_BAND_LABEL: Record<ContextBand, string> = {
  small: 'کوچک (تا ۳۲ هزار توکن)',
  medium: 'متوسط (تا ۱۵۰ هزار توکن)',
  large: 'بزرگ (تا ۶۰۰ هزار توکن)',
  xlarge: 'خیلی‌بزرگ (بیش از ۶۰۰ هزار توکن)',
}

export const CONTEXT_BAND_ORDER: ContextBand[] = ['small', 'medium', 'large', 'xlarge']

export function contextBand(contextWindow: number): ContextBand {
  if (contextWindow <= 32_000) return 'small'
  if (contextWindow <= 150_000) return 'medium'
  if (contextWindow <= 600_000) return 'large'
  return 'xlarge'
}

/**
 * Single source of truth for the model catalog on the client.
 * Fetches from the API with module-level deduplication so multiple
 * components using this hook share a single network request.
 * Falls back to an empty list (with `source: 'unavailable'`) so UI can render
 * a graceful empty/error state instead of hardcoded data.
 */
export function useCatalog(): UseCatalogState {
  const [state, setState] = useState<UseCatalogState>({
    models: cachedData?.data ?? [],
    loading: !cachedData,
    error: false,
    source: cachedData?.source ?? 'loading',
  })

  useEffect(() => {
    let cancelled = false
    fetchCatalog()
      .then((data: CatalogResponse) => {
        if (cancelled) return
        setState({
          models: data?.data ?? [],
          loading: false,
          error: false,
          source: data?.source ?? 'unknown',
        })
      })
      .catch(() => {
        if (cancelled) return
        setState({ models: [], loading: false, error: true, source: 'unavailable' })
      })
    return () => {
      cancelled = true
    }
  }, [])

  return state
}
