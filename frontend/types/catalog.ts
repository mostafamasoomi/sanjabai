export type Currency = 'IRR' | 'IRT'
export type Availability = 'available' | 'degraded' | 'maintenance' | 'disabled'
export type CatalogAudience = 'consumer' | 'developer' | 'team'

/**
 * Live health, measured by the backend from a mix of synthetic probes and the
 * outcomes of real requests.
 *
 * `unknown` means "no samples in the current window" — a model nobody has
 * exercised yet, not a broken one. Treat it as usable; hiding unknowns would
 * empty the picker on a fresh deployment.
 */
export type HealthStatus = 'healthy' | 'degraded' | 'down' | 'unknown'

export type ModelHealth = {
  status: HealthStatus
  /** 0–1 over the rollup window, or null when there are no samples. */
  successRate: number | null
  latencyP50Ms: number | null
  latencyP95Ms: number | null
  sampleCount: number
  lastOkAt: string | null
  /** Short reason code such as `timeout` or `http_502`. Never a raw body. */
  lastError: string | null
  checkedAt: string | null
}

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
  /** Absent on responses from an older backend; treat as unknown. */
  health?: ModelHealth
}

export type CatalogResponse = {
  data: ModelCatalogItem[]
  generatedAt: string
  source: 'approved-catalog'
}

/** GET /api/models/health — backs the /status page. */
export type ModelHealthEntry = ModelHealth & {
  id: string
  displayName: string
}

export type HealthSummary = {
  overall: 'operational' | 'degraded' | 'down'
  counts: Record<HealthStatus, number>
  upstreams: { name: string; ok: boolean; latencyMs: number; error: string | null }[]
  models: ModelHealthEntry[]
  windowMinutes: number
  generatedAt: string
}
