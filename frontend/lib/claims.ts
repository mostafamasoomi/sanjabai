import type { ModelCatalogItem } from '@/types/catalog'

export type ClaimType = 'fact' | 'estimate' | 'marketing' | 'illustrative'

export type Claim = {
  claimKey: string
  copyFa: string
  copyEn: string
  claimType: ClaimType
  source?: string
  verifiedAt?: string
  expiresAt?: string
  owner?: string
  audience?: string[]
  featureFlag?: string
  fallbackCopy: string
}

/** Safe, source-backed content. Unsupported numbers/providers are intentionally absent. */
export const claims: Claim[] = [
  {
    claimKey: 'workspace_promise',
    copyFa: 'چند مدل هوش مصنوعی را از یک workspace انتخاب و استفاده کنید.',
    copyEn: 'Choose and use multiple AI models from one workspace.',
    claimType: 'marketing',
    owner: 'product',
    fallbackCopy: 'یک workspace برای کار با مدل‌های هوش مصنوعی.',
  },
  {
    claimKey: 'currency_transparency',
    copyFa: 'هزینه هر درخواست پیش از ارسال، در صورت فراهم بودن قیمت مدل، نمایش داده می‌شود.',
    copyEn: 'The estimated request cost is shown before sending when model pricing is available.',
    claimType: 'fact',
    source: 'catalog-pricing-contract',
    owner: 'finance',
    fallbackCopy: 'قیمت مدل را پیش از ارسال بررسی کنید.',
  },
]

export function getClaim(key: string, lang: 'fa' | 'en' = 'fa'): string {
  const claim = claims.find((item) => item.claimKey === key)
  if (!claim) return ''
  return lang === 'en' ? claim.copyEn : claim.copyFa
}

/** The one filter that defines "how many models we offer" — models actually
 *  `available` right now, per the live catalog. Factored out of
 *  `modelCountLabel` so any caller that just needs the number (not a full
 *  sentence) uses the identical rule instead of re-deriving it. */
export function modelCount(models: ModelCatalogItem[]): number {
  return models.filter((model) => model.availability === 'available').length
}

export function modelCountLabel(models: ModelCatalogItem[], lang: 'fa' | 'en' = 'fa'): string {
  const available = modelCount(models)
  return lang === 'en'
    ? `${available} available model${available === 1 ? '' : 's'}`
    : `${available} مدل در دسترس`
}

/**
 * Server-side live model count for `generateMetadata()` in a Server
 * Component (app/layout.tsx, app/page.tsx). Those run before any request
 * hits Next's `/api/*` rewrite, so — unlike `useCatalog()` — this goes
 * straight at the backend. Returns `null` on any failure (network, bad
 * shape, non-2xx) so a caller can fall back to count-free copy instead of
 * crashing metadata generation, which runs on every request.
 *
 * Not a hook: safe to call from a Server Component. Do not call from a
 * Client Component render — use `useCatalog()` + `modelCount()` there.
 */
export async function fetchLiveModelCount(): Promise<number | null> {
  try {
    const base = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'
    const res = await fetch(`${base}/catalog/models`, { cache: 'no-store' })
    if (!res.ok) return null
    const body = (await res.json()) as { data?: ModelCatalogItem[] }
    if (!Array.isArray(body?.data)) return null
    const count = modelCount(body.data)
    return count > 0 ? count : null
  } catch {
    return null
  }
}
