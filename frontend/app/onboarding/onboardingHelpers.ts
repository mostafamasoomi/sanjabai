import { priceBand } from '@/lib/useCatalog'
import { type ModelCatalogItem } from '@/types/catalog'
import { fmt } from '@/lib/i18n'
import type { Lang } from '@/components/LanguageToggle'
import { onboardingHelpersStrings } from './onboardingHelpers.strings'
import { type Goal, type Recommendation } from './types'
import { FAVORITES_KEY } from './constants'

export function recommendFor(goal: Goal, models: ModelCatalogItem[], favoriteIds: string[], lang: Lang): Recommendation {
  const s = onboardingHelpersStrings(lang)
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
      badgeLabel: s.priceBand[priceBand(match, models)],
      description: match.description,
      pricing: match.pricing,
      contextWindow: match.contextWindow,
      fromCatalog: true,
      id: match.id,
    }
  }
  return {
    // goal.fallbackModel/fallbackProvider are well-known example brand names
    // (e.g. "Claude Sonnet 4" / "Anthropic") -- Latin in both languages, not
    // translated.
    displayName: goal.fallbackModel,
    badgeLabel: goal.fallbackProvider,
    fromCatalog: false,
  }
}

export function formatPrice(p: ModelCatalogItem['pricing'] | undefined, lang: Lang): string {
  if (!p) return ''
  const s = onboardingHelpersStrings(lang)
  const f = fmt(lang)
  const cur = s.currency(p.currency)
  return s.perMillionTokens(f.num(p.inputPerMillion), f.num(p.outputPerMillion), cur)
}

export function formatPriceShort(p: ModelCatalogItem['pricing'] | undefined, lang: Lang): string {
  if (!p) return ''
  const s = onboardingHelpersStrings(lang)
  const f = fmt(lang)
  const cur = s.currency(p.currency)
  return s.inputOutputShort(f.num(p.inputPerMillion), f.num(p.outputPerMillion), cur)
}

export function formatContext(n: number | undefined, lang: Lang): string {
  if (!n) return ''
  const s = onboardingHelpersStrings(lang)
  const f = fmt(lang)
  // `M` / `K` are Latin runs: in an RTL paragraph they were placed before
  // the number they abbreviate. A Persian unit word carries the same
  // meaning safely; English keeps the compact `M`/`K` form as-is.
  return s.tokens(f.compact(n))
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
