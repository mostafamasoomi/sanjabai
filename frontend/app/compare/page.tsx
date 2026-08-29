'use client'

import { useState, useEffect, useMemo } from 'react'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { useCatalog, priceBand, PRICE_BAND_LABEL } from '@/lib/useCatalog'
import { type ModelCatalogItem } from '@/types/catalog'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { Skeleton, EmptyState, toast } from '@/components/ui'
import MarkdownRenderer from '@/app/chat/components/MarkdownRenderer'
import ModelPicker from '@/app/chat/components/ModelPicker'
import { comparePageStrings } from './page.strings'
import { tourAnchor } from '@/components/tour/anchors'

/* ═══════════════════════════════════════════════════════════════════════════
   Model Compare — Split view side-by-side
   Pick two models, enter a prompt, see results + stats simultaneously.
   ═══════════════════════════════════════════════════════════════════════════ */

type CompareResult = {
  model: string
  content: string
  elapsed: number
  input_tokens: number
  output_tokens: number
  cost: number
  error: string | null
}

type CompareResponse = {
  model_a: CompareResult
  model_b: CompareResult
  faster: 'model_a' | 'model_b' | null
  cheaper: 'model_a' | 'model_b' | null
  messages: { role: string; content: string }[]
}

type Side = 'a' | 'b'

function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const sz = size === 'sm' ? 16 : size === 'lg' ? 32 : 24
  return (
    <svg className="animate-spin" width={sz} height={sz} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

function formatElapsed(sec: number): string {
  if (sec < 1) return `${(sec * 1000).toFixed(0)}ms`
  return `${sec.toFixed(1)}s`
}

export default function ComparePage() {
  const { token } = useAuth()
  const lang = useLang()
  const s = comparePageStrings(lang)
  const f = fmt(lang)
  const { models, loading: catalogLoading, error: catalogError } = useCatalog()
  const [modelA, setModelA] = useState<ModelCatalogItem | null>(null)
  const [modelB, setModelB] = useState<ModelCatalogItem | null>(null)
  const [comparedModelA, setComparedModelA] = useState<ModelCatalogItem | null>(null)
  const [comparedModelB, setComparedModelB] = useState<ModelCatalogItem | null>(null)
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<CompareResponse | null>(null)
  const [error, setError] = useState('')

  // Default to first two working models from catalog
  useEffect(() => {
    if (models.length > 0 && !modelA && !modelB) {
      setModelA(models[0])
      if (models.length > 1) setModelB(models[1])
    }
  }, [models, modelA, modelB])

  useEffect(() => {
    if (catalogError) toast(s.fetchModelsError, 'error')
  }, [catalogError, s])

  const canCompare = useMemo(
    () => modelA && modelB && modelA.id !== modelB.id && prompt.trim() && !busy,
    [modelA, modelB, prompt, busy],
  )

  const handleCompare = async () => {
    if (!canCompare || !modelA || !modelB) return

    setBusy(true)
    setResults(null)
    setError('')
    setComparedModelA(modelA)
    setComparedModelB(modelB)

    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    try {
      const res = await apiFetch('/api/v1/compare', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          model_a: modelA.providerModelId || modelA.id,
          model_b: modelB.providerModelId || modelB.id,
          messages: [{ role: 'user', content: prompt.trim() }],
        }),
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        // errData?.error?.message / errData?.detail are backend-sourced error
        // messages (Persian only for now) -- see the i18n handoff report.
        const msg = errData?.error?.message || errData?.detail || s.serverError(f.num(res.status))
        if (res.status === 429) throw new Error('INSUFFICIENT_BALANCE')
        throw new Error(msg)
      }

      const data: CompareResponse = await res.json()
      setResults(data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : s.connectionError
      if (msg === 'INSUFFICIENT_BALANCE') {
        setError(s.insufficientBalance)
      } else {
        setError(msg)
      }
    } finally {
      setBusy(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      handleCompare()
    }
  }

  const renderResultPanel = (side: Side, model: ModelCatalogItem | null, result: CompareResult | null) => {
    const isFaster = results?.faster === `model_${side}`
    const isCheaper = results?.cheaper === `model_${side}`

    return (
      <div className="compare-panel">
        {/* Panel header */}
        <div className="compare-panel-header">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: 'var(--accent-dim)' }}>
              <Icon name="models" size={16} className="text-[var(--accent)]" />
            </div>
            <div className="min-w-0">
              {model ? (
                <>
                  <span className="compare-model-name" dir="ltr">{model.displayName}</span>
                  {/* PRICE_BAND_LABEL (lib/useCatalog.ts) is a hardcoded
                      Persian record outside this directory's allowed scope --
                      it renders Persian even in the English UI. See the i18n
                      handoff report. */}
                  <span className="compare-model-provider">{PRICE_BAND_LABEL[priceBand(model, models)]}</span>
                </>
              ) : (
                <span className="text-sm text-[var(--text-muted)]">{s.noModelSelected}</span>
              )}
            </div>
          </div>

          {/* Winner badges */}
          {result && !result.error && (
            <div className="compare-badges">
              {isFaster && (
                <span className="compare-badge compare-badge-fast" title={s.faster}>
                  ⚡ {s.faster}
                </span>
              )}
              {isCheaper && (
                <span className="compare-badge compare-badge-cheap" title={s.cheaper}>
                  💰 {s.cheaper}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Stats bar */}
        {result && !result.error && (
          <div className="compare-stats">
            <div className="compare-stat">
              <span className="compare-stat-label">{s.time}</span>
              <span className={`compare-stat-value ${isFaster ? 'compare-stat-winner' : ''}`}>
                {formatElapsed(result.elapsed)}
              </span>
            </div>
            <div className="compare-stat">
              <span className="compare-stat-label">{s.tokensInput}</span>
              <span className="compare-stat-value num">{f.num(result.input_tokens)}</span>
            </div>
            <div className="compare-stat">
              <span className="compare-stat-label">{s.tokensOutput}</span>
              <span className="compare-stat-value num">{f.num(result.output_tokens)}</span>
            </div>
            <div className="compare-stat">
              <span className="compare-stat-label">{s.cost}</span>
              {/* Toman via f.price — no page-local ÷1000 formatter, no "IRT"
                  label on a divided value (that was the old 10x-style trap). */}
              <span className={`compare-stat-value ${isCheaper ? 'compare-stat-winner' : ''}`}>
                {f.price(result.cost)}
              </span>
            </div>
          </div>
        )}

        {/* Content area */}
        <div className="compare-content">
          {busy ? (
            <div className="compare-loading">
              <Spinner size="md" />
              <span className="text-sm text-[var(--text-secondary)] mt-2">{s.receiving}</span>
            </div>
          ) : result?.error ? (
            <div className="compare-error">
              <Icon name="close" size={20} className="text-[var(--danger)]" />
              {/* result.error is a backend-sourced error message (Persian
                  only for now) -- see the i18n handoff report. */}
              <span className="text-sm text-[var(--danger)]">{result.error}</span>
            </div>
          ) : result?.content ? (
            <div className="compare-markdown">
              <MarkdownRenderer content={result.content} />
            </div>
          ) : (
            <div className="compare-placeholder">
              <Icon name="compare" size={24} className="text-[var(--text-muted)]" />
              <span className="text-sm text-[var(--text-muted)]">{s.placeholder}</span>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="compare-page">
      {/* Header */}
      <div className="compare-header">
        <div>
          <h1 className="text-2xl font-bold text-gradient">{s.title}</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            {s.subtitle}
          </p>
        </div>
      </div>

      {/* Model pickers + prompt */}
      <div className="card">
        <div className="compare-controls">
          {/* Model A picker */}
          <div className="compare-picker-col">
            <label className="compare-picker-label">
              <span className="compare-picker-badge a">{s.modelA}</span>
            </label>
            {catalogLoading ? (
              <Skeleton className="w-full" height="2.5rem" />
            ) : (
              <ModelPicker
                models={models.filter(m => m.id !== modelB?.id)}
                selected={modelA}
                onSelect={setModelA}
                loading={false}
                disabled={busy}
              />
            )}
          </div>

          {/* VS divider */}
          <div className="compare-vs">
            <span>{s.vs}</span>
          </div>

          {/* Model B picker */}
          <div className="compare-picker-col">
            <label className="compare-picker-label">
              <span className="compare-picker-badge b">{s.modelB}</span>
            </label>
            {catalogLoading ? (
              <Skeleton className="w-full" height="2.5rem" />
            ) : (
              <ModelPicker
                models={models.filter(m => m.id !== modelA?.id)}
                selected={modelB}
                onSelect={setModelB}
                loading={false}
                disabled={busy}
              />
            )}
          </div>
        </div>

        {/* Prompt input */}
        <div className="compare-input-row">
          <textarea dir="auto"
            className="input flex-1"
            {...tourAnchor('compare.prompt')}
            rows={2}
            placeholder={s.promptPlaceholder}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={busy}
          />
          <button
            className="btn btn-primary compare-submit-btn"
            onClick={handleCompare}
            disabled={!canCompare}
          >
            {busy ? (
              <>
                <Spinner size="sm" />
                {s.comparing}
              </>
            ) : (
              <>
                <Icon name="compare" size={16} />
                {s.compare}
              </>
            )}
          </button>
        </div>

        {error && (
          <div className="compare-error-banner">
            <Icon name="close" size={16} />
            <span>{error}</span>
          </div>
        )}
      </div>

      {/* Empty state */}
      {!catalogLoading && !catalogError && models.length === 0 && (
        <EmptyState
          icon="compare"
          title={s.noModelsTitle}
          description={s.noModelsDesc}
        />
      )}

      {/* Results — split view */}
      <div className="compare-results">
        {renderResultPanel('a', comparedModelA || modelA, results?.model_a ?? null)}
        {renderResultPanel('b', comparedModelB || modelB, results?.model_b ?? null)}
      </div>
    </div>
  )
}