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
