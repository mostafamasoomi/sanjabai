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

export function modelCountLabel(models: ModelCatalogItem[], lang: 'fa' | 'en' = 'fa'): string {
  const available = models.filter((model) => model.availability === 'available').length
  return lang === 'en'
    ? `${available} available model${available === 1 ? '' : 's'}`
    : `${available} مدل در دسترس`
}
