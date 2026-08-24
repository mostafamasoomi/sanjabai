import { priceBand, PRICE_BAND_LABEL } from '@/lib/useCatalog'
import { type ModelCatalogItem } from '@/types/catalog'
import { faNum, faCompact } from '@/lib/format'
import { type Goal, type Recommendation } from './types'
import { FAVORITES_KEY } from './constants'

export function recommendFor(goal: Goal, models: ModelCatalogItem[], favoriteIds: string[]): Recommendation {
  const kw = goal.keywords
  // First try to find a matching model among favorites
  const favorites = models.filter((m) => favoriteIds.includes(m.id))
  const matchInFavorites = favorites.find((m) => {
    const caps = (m.capabilities || []).map((c) => c.toLowerCase())
    const rec = (m.recommendedFor || []).map((r) => r.toLowerCase())
    return kw.some((k) => caps.some((c) => c.includes(k)) || rec.some((r) => r.includes(k)))
  })
  const match = matchInFavorites || models.find((m) => {
    const caps = (m.capabilities || []).map((c) => c.toLowerCase())
    const rec = (m.recommendedFor || []).map((r) => r.toLowerCase())
    return kw.some((k) => caps.some((c) => c.includes(k)) || rec.some((r) => r.includes(k)))
  })
  if (match) {
    return {
      displayName: match.displayName,
      badgeLabel: PRICE_BAND_LABEL[priceBand(match, models)],
      description: match.description,
      pricing: match.pricing,
      contextWindow: match.contextWindow,
      fromCatalog: true,
      id: match.id,
    }
  }
  return {
    displayName: goal.fallbackModel,
    badgeLabel: goal.fallbackProvider,
    fromCatalog: false,
  }
}

export function formatPrice(p?: ModelCatalogItem['pricing']): string {
  if (!p) return ''
  const cur = p.currency === 'IRT' ? 'تومان' : p.currency === 'IRR' ? 'ریال' : p.currency
  return `هر ۱ میلیون توکن — ورودی ${p.inputPerMillion} · خروجی ${p.outputPerMillion} ${cur}`
}

export function formatPriceShort(p?: ModelCatalogItem['pricing']): string {
  if (!p) return ''
  const cur = p.currency === 'IRT' ? 'تومان' : p.currency === 'IRR' ? 'ریال' : p.currency
  const fmt = faNum
  return `ورودی ${fmt(p.inputPerMillion)} · خروجی ${fmt(p.outputPerMillion)} ${cur}`
}

export function formatContext(n?: number): string {
  if (!n) return ''
  // `M` / `K` are Latin runs: in an RTL paragraph they were placed before
  // the number they abbreviate. Persian words carry the same meaning safely.
  return `${faCompact(n)} توکن`
}

export function loadFavorites(): string[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = localStorage.getItem(FAVORITES_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

export function saveFavorites(ids: string[]) {
  try {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify(ids))
  } catch {
    // ignore
  }
}
