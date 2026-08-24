import { type ModelCatalogItem } from '@/types/catalog'
import { type IconName } from '@/components/ui/Icon'

export type Goal = {
  id: string
  label: string
  icon: IconName
  hint: string
  /** keywords matched against catalog capabilities / recommendedFor */
  keywords: string[]
  /** used only when the live catalog is unavailable */
  fallbackModel: string
  fallbackProvider: string
}

export type Recommendation = {
  displayName: string
  /** A price-band label ("رایگان"/"استاندارد"/"حرفه‌ای") for a live catalog
      match, or a well-known example brand name for the static fallback used
      when the catalog is unavailable. Never the internal routing provider —
      that field isn't part of the public catalog contract. */
  badgeLabel: string
  description?: string
  pricing?: ModelCatalogItem['pricing']
  contextWindow?: number
  fromCatalog: boolean
  id?: string
}
