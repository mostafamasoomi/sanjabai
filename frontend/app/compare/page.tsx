'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import { Spinner, Skeleton, EmptyState, toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { useCatalog } from '@/lib/useCatalog'
import type { ModelCatalogItem } from '@/types/catalog'

type CompareResult = { model: string; label: string; content: string; error?: string }

export default function ComparePage() {
  const { token } = useAuth()
  const { models, loading, error } = useCatalog()
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<CompareResult[]>([])
  const [selected, setSelected] = useState<string[]>([])

  // Default to first 3 models once catalog loads
  useEffect(() => {
    if (models.length > 0 && selected.length === 0) {
      setSelected(models.slice(0, 3).map((m) => m.id))
    }
  }, [models, selected.length])

  useEffect(() => {
    if (error) toast('خطا در دریافت فهرست مدلها', 'error')
  }, [error])

  const toggle = (id: string) => {
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id)
      if (prev.length >= 4) {
        toast('حداکثر ۴ مدل قابل مقایسه است', 'info')
        return prev
      }
      return [...prev, id]
    })
  }

  const compare = async () => {
    if (!prompt.trim() || busy) return
    const chosen = models.filter((m) => selected.includes(m.id))
    if (chosen.length < 2) {
      toast('حداقل ۲ مدل انتخاب کنید', 'error')
      return
    }

    setBusy(true)
    setResults([])

    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const promises = chosen.map(async (m) => {
      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            model: m.id,
            messages: [{ role: 'user', content: prompt }],
          }),
        })
        const data = await res.json()
        return { model: m.id, label: m.displayName, content: data?.choices?.[0]?.message?.content || '[بدون پاسخ]' }
      } catch {
        return { model: m.id, label: m.displayName, content: '', error: 'خطا در ارتباط' }
      }
    })

    const allResults = await Promise.all(promises)
    setResults(allResults)
    setBusy(false)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gradient">مقایسه مدلها</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-2">یک prompt به چند مدل ارسال کنید و پاسخها را مقایسه کنید</p>
      </div>

      {/* Model Selection */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Icon name="models" size={16} className="text-[var(--accent)]" />
          <span className="text-sm font-semibold text-[var(--text-primary)]">انتخاب مدلها</span>
          <span className="badge badge-accent">{selected.length} انتخاب شده</span>
        </div>
        <div className="flex flex-wrap gap-2 mb-4">
          {loading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="w-24" height="2rem" />
            ))
          ) : models.length === 0 ? (
            <span className="text-sm text-[var(--text-muted)]">مدلی برای مقایسه یافت نشد.</span>
          ) : (
            models.map((m) => {
              const isSelected = selected.includes(m.id)
              return (
                <button
                  key={m.id}
                  onClick={() => toggle(m.id)}
                  className={`btn btn-sm transition-all ${isSelected ? 'btn-primary' : 'btn-ghost'}`}
                  style={isSelected ? { boxShadow: '0 0 12px rgba(99, 102, 241, 0.3)' } : {}}
                >
                  {isSelected && <Icon name="check" size={12} />}
                  {m.displayName}
                </button>
              )
            })
          )}
        </div>

        {/* Prompt input */}
        <div className="flex gap-3">
          <textarea
            className="input flex-1"
            rows={3}
            placeholder="prompt خود را بنویسید..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) compare()
            }}
          />
          <button
            className="btn btn-primary self-end"
            onClick={compare}
            disabled={busy || !prompt.trim() || selected.length < 2}
          >
            {busy ? <Spinner size="sm" /> : <Icon name="compare" size={16} />}
            {busy ? 'در حال مقایسه...' : 'مقایسه'}
          </button>
        </div>
        <p className="text-xs text-[var(--text-muted)] mt-2">Ctrl+Enter برای ارسال</p>
      </div>

      {/* Empty state */}
      {!loading && !error && models.length === 0 && (
        <EmptyState
          icon="compare"
          title="مدلی برای مقایسه نیست"
          description="فهرست مدلها خالی است؛ پس از بارگذاری مدلها میتوانید آنها را مقایسه کنید."
        />
      )}

      {/* Loading indicator */}
      {busy && (
        <div className="text-center py-8">
          <Spinner size="lg" />
          <p className="text-sm text-[var(--text-secondary)] mt-3">در حال دریافت پاسخ از مدلها...</p>
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {results.map((r, i) => (
            <div
              key={r.model}
              className="card"
              style={{ animationDelay: `${i * 100}ms`, animation: 'slideUp 0.3s ease both' }}
            >
              <div className="flex items-center gap-2 mb-3 pb-3 border-b border-[var(--border)]">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'var(--accent-dim)' }}>
                  <Icon name="models" size={16} className="text-[var(--accent)]" />
                </div>
                <span className="badge badge-accent font-semibold">{r.label}</span>
              </div>
              {r.error ? (
                <p className="text-sm text-[var(--danger)]">{r.error}</p>
              ) : (
                <div className="text-sm leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto">
                  {r.content}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
