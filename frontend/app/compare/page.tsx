'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import { Spinner, Skeleton, EmptyState, toast } from '@/components/ui'
import { useCatalog } from '@/lib/useCatalog'

type CompareResult = { model: string; label: string; content: string; error?: string }

export default function ComparePage() {
  const { token } = useAuth()
  const { models, loading, error } = useCatalog()
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<CompareResult[]>([])
  const [selected, setSelected] = useState<string[]>([])

  // Default to comparing every model available in the live catalog once it loads.
  useEffect(() => {
    if (models.length > 0 && selected.length === 0) {
      setSelected(models.map((m) => m.id))
    }
  }, [models, selected.length])

  // Surface catalog load failures as a toast (design-system error state).
  useEffect(() => {
    if (error) toast('خطا در دریافت فهرست مدلها', 'error')
  }, [error])

  const toggle = (id: string) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const compare = async () => {
    if (!prompt.trim() || busy) return
    const chosen = models.filter((m) => selected.includes(m.id))
    if (chosen.length === 0) return

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

    const results = await Promise.all(promises)
    setResults(results)
    setBusy(false)
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">مقایسه مدلها</h1>
      <p className="text-sm text-[var(--text-dim)]">یک prompt به چند مدل ارسال کنید و پاسخها را مقایسه کنید</p>

      <div className="card">
        <div className="flex flex-wrap gap-2 mb-4">
          {loading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="w-24" height="1.75rem" />
            ))
          ) : models.length === 0 ? (
            <span className="text-sm text-[var(--text-dim)]">مدلی برای مقایسه یافت نشد.</span>
          ) : (
            models.map((m) => (
              <button
                key={m.id}
                onClick={() => toggle(m.id)}
                className={`btn btn-sm ${selected.includes(m.id) ? 'btn-primary' : 'btn-ghost'}`}
              >
                {m.displayName}
              </button>
            ))
          )}
        </div>

        <div className="flex gap-3">
          <textarea
            className="input flex-1"
            rows={4}
            placeholder="prompt خود را بنویسید..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && compare()}
          />
          <button className="btn btn-primary self-end" onClick={compare} disabled={busy || !prompt.trim() || selected.length === 0}>
            {busy ? <Spinner size="sm" /> : 'مقایسه'}
          </button>
        </div>
      </div>

      {!loading && !error && models.length === 0 && (
        <EmptyState
          icon="compare"
          title="مدلی برای مقایسه نیست"
          description="فهرست مدلها خالی است؛ پس از بارگذاری مدلها میتوانید آنها را مقایسه کنید."
        />
      )}

      {busy && (
        <div className="text-center py-8">
          <Spinner size="lg" />
          <p className="text-sm text-[var(--text-dim)] mt-3">در حال دریافت پاسخ از مدلها...</p>
        </div>
      )}

      {results.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {results.map((r) => (
            <div key={r.model} className="card">
              <div className="flex items-center gap-2 mb-3">
                <span className="badge badge-accent">{r.label}</span>
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
