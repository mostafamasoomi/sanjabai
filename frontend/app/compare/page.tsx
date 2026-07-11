'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import { Spinner } from '@/components/ui'

type Model = { id: string }

const COMPARE_MODELS = [
  'kr/gpt-4o',
  'kr/claude-3.5-sonnet',
  'kr/gemini-2.0-flash',
  'kr/deepseek-3.2',
]

export default function ComparePage() {
  const { token } = useAuth()
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<{ model: string; content: string; error?: string }[]>([])
  const [models, setModels] = useState<Model[]>([])

  useEffect(() => {
    fetch('/api/models')
      .then((r) => r.json())
      .then((d) => setModels(d.data || []))
      .catch(() => {})
  }, [])

  const compare = async () => {
    if (!prompt.trim() || busy) return
    setBusy(true)
    setResults([])

    const selectedModels = COMPARE_MODELS.filter((m) => models.some((x) => x.id === m))
    if (selectedModels.length === 0) return

    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const promises = selectedModels.map(async (model) => {
      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            model,
            messages: [{ role: 'user', content: prompt }],
          }),
        })
        const data = await res.json()
        return { model, content: data?.choices?.[0]?.message?.content || '[بدون پاسخ]' }
      } catch {
        return { model, content: '', error: 'خطا در ارتباط' }
      }
    })

    const results = await Promise.all(promises)
    setResults(results)
    setBusy(false)
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">مقایسه مدل‌ها</h1>
      <p className="text-sm text-[var(--text-dim)]">یک prompt به چند مدل ارسال کنید و پاسخ‌ها را مقایسه کنید</p>

      <div className="card">
        <div className="flex gap-3">
          <textarea
            className="input flex-1"
            rows={4}
            placeholder="prompt خود را بنویسید..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && compare()}
          />
          <button className="btn btn-primary self-end" onClick={compare} disabled={busy || !prompt.trim()}>
            {busy ? <Spinner size="sm" /> : 'مقایسه'}
          </button>
        </div>
      </div>

      {busy && (
        <div className="text-center py-8">
          <Spinner size="lg" />
          <p className="text-sm text-[var(--text-dim)] mt-3">در حال دریافت پاسخ از مدل‌ها...</p>
        </div>
      )}

      {results.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {results.map((r) => (
            <div key={r.model} className="card">
              <div className="flex items-center gap-2 mb-3">
                <span className="badge badge-accent">{r.model}</span>
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