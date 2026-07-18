'use client'

import { useState, useEffect, useMemo } from 'react'
import { useAuth } from '@/lib/auth'
import { useCatalog } from '@/lib/useCatalog'
import { type ModelCatalogItem } from '@/types/catalog'
import { Icon } from '@/components/ui/Icon'
import { Skeleton, EmptyState, toast } from '@/components/ui'
import MarkdownRenderer from '@/app/chat/components/MarkdownRenderer'
import ModelPicker from '@/app/chat/components/ModelPicker'

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

function formatCost(tomans: number): string {
  if (tomans >= 1000) return `${(tomans / 1000).toFixed(1)}k`
  return `${tomans}`
}

export default function ComparePage() {
  const { token } = useAuth()
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
    if (catalogError) toast('خطا در دریافت فهرست مدلها', 'error')
  }, [catalogError])

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
      const res = await fetch('/api/v1/compare', {
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
        const msg = errData?.error?.message || errData?.detail || `خطای سرور: ${res.status}`
        if (res.status === 429) throw new Error('INSUFFICIENT_BALANCE')
        throw new Error(msg)
      }

      const data: CompareResponse = await res.json()
      setResults(data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'خطا در ارتباط'
      if (msg === 'INSUFFICIENT_BALANCE') {
        setError('موجودی کیف پول کافی نیست. لطفاً حساب خود را شارژ کنید.')
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
 <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 bg-accent-dim" >
              <Icon name="models" size={16} className="text-[var(--accent)]" />
            </div>
            <div className="min-w-0">
              {model ? (
                <>
                  <span className="compare-model-name" dir="ltr">{model.displayName}</span>
                  <span className="compare-model-provider" dir="ltr">{model.provider}</span>
                </>
              ) : (
                <span className="text-sm text-[var(--text-muted)]">مدل انتخاب نشده</span>
              )}
            </div>
          </div>

          {/* Winner badges */}
          {result && !result.error && (
            <div className="compare-badges">
              {isFaster && (
                <span className="compare-badge compare-badge-fast" title="سریعتر">
                  ⚡ سریعتر
                </span>
              )}
              {isCheaper && (
                <span className="compare-badge compare-badge-cheap" title="ارزانتر">
                  💰 ارزانتر
                </span>
              )}
            </div>
          )}
        </div>

        {/* Stats bar */}
        {result && !result.error && (
          <div className="compare-stats">
            <div className="compare-stat">
              <span className="compare-stat-label">زمان</span>
              <span className={`compare-stat-value ${isFaster ? 'compare-stat-winner' : ''}`}>
                {formatElapsed(result.elapsed)}
              </span>
            </div>
            <div className="compare-stat">
              <span className="compare-stat-label">توکن ورودی</span>
              <span className="compare-stat-value">{result.input_tokens.toLocaleString()}</span>
            </div>
            <div className="compare-stat">
              <span className="compare-stat-label">توکن خروجی</span>
              <span className="compare-stat-value">{result.output_tokens.toLocaleString()}</span>
            </div>
            <div className="compare-stat">
              <span className="compare-stat-label">هزینه</span>
              <span className={`compare-stat-value ${isCheaper ? 'compare-stat-winner' : ''}`}>
                {formatCost(result.cost)} IRT
              </span>
            </div>
          </div>
        )}

        {/* Content area */}
        <div className="compare-content">
          {busy ? (
            <div className="compare-loading">
              <Spinner size="md" />
              <span className="text-sm text-[var(--text-secondary)] mt-2">در حال دریافت پاسخ...</span>
            </div>
          ) : result?.error ? (
            <div className="compare-error">
              <Icon name="close" size={20} className="text-[var(--danger)]" />
              <span className="text-sm text-[var(--danger)]">{result.error}</span>
            </div>
          ) : result?.content ? (
            <div className="compare-markdown">
              <MarkdownRenderer content={result.content} />
            </div>
          ) : (
            <div className="compare-placeholder">
              <Icon name="compare" size={24} className="text-[var(--text-muted)]" />
              <span className="text-sm text-[var(--text-muted)]">پاسخ مدل در اینجا نمایش داده می‌شود</span>
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
          <h1 className="text-2xl font-bold text-gradient">مقایسه مدلها</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            دو مدل را انتخاب کنید، یک prompt بنویسید و پاسخ‌ها را کنار هم مقایسه کنید
          </p>
        </div>
      </div>

      {/* Model pickers + prompt */}
      <div className="card">
        <div className="compare-controls">
          {/* Model A picker */}
          <div className="compare-picker-col">
            <label className="compare-picker-label">
              <span className="compare-picker-badge a">مدل A</span>
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
            <span>VS</span>
          </div>

          {/* Model B picker */}
          <div className="compare-picker-col">
            <label className="compare-picker-label">
              <span className="compare-picker-badge b">مدل B</span>
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
          <textarea dir="rtl"
            className="input flex-1"
            rows={2}
            placeholder="prompt خود را بنویسید... (Ctrl+Enter برای ارسال)"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={busy}
            dir="auto"
          />
          <button
            className="btn btn-primary compare-submit-btn"
            onClick={handleCompare}
            disabled={!canCompare}
          >
            {busy ? (
              <>
                <Spinner size="sm" />
                در حال مقایسه...
              </>
            ) : (
              <>
                <Icon name="compare" size={16} />
                مقایسه
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
          title="مدلی برای مقایسه نیست"
          description="فهرست مدلها خالی است؛ پس از بارگذاری مدلها می‌توانید آنها را مقایسه کنید."
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