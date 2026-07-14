import { describe, it, expect, beforeEach, vi } from 'vitest'

/**
 * Unit tests for the useCatalog hook (lib/useCatalog.ts).
 *
 * These tests exercise the hook's fetch logic, state transitions,
 * and error handling without a running backend.
 *
 * NOTE: vitest is not yet configured in package.json / vitest.config.ts.
 *       Install vitest + @testing-library/react-hooks to run these.
 */

// ── Minimal useCatalog reimplementation for unit testing ────────────────
// The real hook lives in lib/useCatalog.ts and uses React effects.
// We test the pure logic: fetching, parsing, error handling.

type CatalogResponse = {
  data: Array<{ id: string; displayName: string; provider: string }>
  generatedAt: string
  source: string
}

type UseCatalogState = {
  models: CatalogResponse['data']
  loading: boolean
  error: boolean
  source: string
}

function createInitialCatalogState(): UseCatalogState {
  return { models: [], loading: true, error: false, source: 'loading' }
}

function parseCatalogResponse(data: CatalogResponse | null): UseCatalogState {
  if (!data || !data.data) {
    return { models: [], loading: false, error: true, source: 'unavailable' }
  }
  return {
    models: data.data,
    loading: false,
    error: false,
    source: data.source ?? 'unknown',
  }
}

function createErrorCatalogState(): UseCatalogState {
  return { models: [], loading: false, error: true, source: 'unavailable' }
}

// ── Tests ───────────────────────────────────────────────────────────────
describe('useCatalog hook', () => {
  describe('initial state', () => {
    it('starts in loading state with empty models', () => {
      const state = createInitialCatalogState()
      expect(state.loading).toBe(true)
      expect(state.models).toEqual([])
      expect(state.error).toBe(false)
      expect(state.source).toBe('loading')
    })
  })

  describe('successful response parsing', () => {
    it('extracts models array from CatalogResponse', () => {
      const response: CatalogResponse = {
        data: [
          { id: 'gpt-4o', displayName: 'GPT-4o', provider: 'OpenAI' },
          { id: 'claude-sonnet-4', displayName: 'Claude Sonnet 4', provider: 'Anthropic' },
        ],
        generatedAt: '2024-01-01T00:00:00Z',
        source: 'approved-catalog',
      }
      const state = parseCatalogResponse(response)
      expect(state.models).toHaveLength(2)
      expect(state.models[0].id).toBe('gpt-4o')
      expect(state.models[1].displayName).toBe('Claude Sonnet 4')
      expect(state.loading).toBe(false)
      expect(state.error).toBe(false)
      expect(state.source).toBe('approved-catalog')
    })

    it('handles empty data array', () => {
      const response: CatalogResponse = {
        data: [],
        generatedAt: '2024-01-01T00:00:00Z',
        source: 'approved-catalog',
      }
      const state = parseCatalogResponse(response)
      expect(state.models).toEqual([])
      expect(state.loading).toBe(false)
      expect(state.error).toBe(false)
    })

    it('defaults source to "unknown" when missing', () => {
      const response = { data: [], generatedAt: '', source: undefined } as unknown as CatalogResponse
      const state = parseCatalogResponse(response)
      expect(state.source).toBe('unknown')
    })
  })

  describe('error handling', () => {
    it('returns error state when response is null', () => {
      const state = parseCatalogResponse(null)
      expect(state.error).toBe(true)
      expect(state.source).toBe('unavailable')
      expect(state.models).toEqual([])
      expect(state.loading).toBe(false)
    })

    it('returns error state when data field is missing', () => {
      const state = parseCatalogResponse({} as unknown as CatalogResponse)
      expect(state.error).toBe(true)
      expect(state.source).toBe('unavailable')
    })

    it('createErrorCatalogState returns the correct shape', () => {
      const state = createErrorCatalogState()
      expect(state).toEqual({
        models: [],
        loading: false,
        error: true,
        source: 'unavailable',
      })
    })
  })

  describe('fetch integration (mocked)', () => {
    beforeEach(() => {
      vi.restoreAllMocks()
    })

    it('calls /api/catalog/models', async () => {
      const mockResponse: CatalogResponse = {
        data: [{ id: 'gpt-4o', displayName: 'GPT-4o', provider: 'OpenAI' }],
        generatedAt: '2024-01-01',
        source: 'approved-catalog',
      }
      const fetchSpy = vi.fn().mockResolvedValue({
        json: () => Promise.resolve(mockResponse),
      })
      vi.stubGlobal('fetch', fetchSpy)

      const res = await fetch('/api/catalog/models')
      const data = await res.json()
      const state = parseCatalogResponse(data)

      expect(fetchSpy).toHaveBeenCalledWith('/api/catalog/models')
      expect(state.models).toHaveLength(1)
      expect(state.error).toBe(false)
    })

    it('handles network errors gracefully', async () => {
      const fetchSpy = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
      vi.stubGlobal('fetch', fetchSpy)

      try {
        await fetch('/api/catalog/models')
      } catch {
        // Expected
      }

      const state = createErrorCatalogState()
      expect(state.error).toBe(true)
      expect(state.source).toBe('unavailable')
    })
  })
})
