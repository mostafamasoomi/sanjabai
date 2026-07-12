'use client'

import { useEffect, useState } from 'react'
import { type ModelCatalogItem, type CatalogResponse } from '@/types/catalog'

export type UseCatalogState = {
  models: ModelCatalogItem[]
  loading: boolean
  error: boolean
  source: string
}

/**
 * Single source of truth for the model catalog on the client.
 * Always fetches from the API; never uses a static production model list.
 * Falls back to an empty list (with `source: 'unavailable'`) so UI can render
 * a graceful empty/error state instead of hardcoded data.
 */
export function useCatalog(): UseCatalogState {
  const [state, setState] = useState<UseCatalogState>({
    models: [],
    loading: true,
    error: false,
    source: 'loading',
  })

  useEffect(() => {
    let cancelled = false
    fetch('/api/catalog/models')
      .then((res) => res.json())
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
