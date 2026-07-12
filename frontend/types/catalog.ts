export type Currency = 'IRR' | 'IRT'
export type Availability = 'available' | 'degraded' | 'maintenance' | 'disabled'
export type CatalogAudience = 'consumer' | 'developer' | 'team'

export type ModelCatalogItem = {
  id: string
  providerModelId: string
  provider: string
  displayName: string
  description?: string
  modalities: { input: string[]; output: string[] }
  capabilities: string[]
  recommendedFor: string[]
  contextWindow: number
  maxOutputTokens?: number
  pricing: {
    currency: Currency
    inputPerMillion: number
    outputPerMillion: number
    cachedInputPerMillion?: number
    reasoningPerMillion?: number
    priceVersion: string
    effectiveFrom: string
  }
  availability: Availability
  audience: CatalogAudience[]
  rateLimit?: { requestsPerMinute?: number; concurrency?: number }
  deprecatedAt?: string
  lastVerifiedAt: string
  provenance: 'provider' | 'admin-approved' | 'fallback'
}

export type CatalogResponse = {
  data: ModelCatalogItem[]
  generatedAt: string
  source: 'approved-catalog'
}
