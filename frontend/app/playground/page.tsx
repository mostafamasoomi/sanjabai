'use client'

import { useState, useMemo } from 'react'
import { useAuth } from '@/lib/auth'
import { useCatalog } from '@/lib/useCatalog'
import { type ModelCatalogItem } from '@/types/catalog'
import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { Skeleton, EmptyState, toast } from '@/components/ui'
import MarkdownRenderer from '@/app/chat/components/MarkdownRenderer'
import ModelPicker from '@/app/chat/components/ModelPicker'

/* ═══════════════════════════════════════════════════════════════════════════
   Playground — send a raw /v1/chat/completions request and inspect the
   response, with an equivalent curl snippet for API integration.
   ═══════════════════════════════════════════════════════════════════════════ */

type ChatResponse = {
  id?: string
  choices?: { message?: { content?: string } }[]
  usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number }
  error?: { message?: string }
  detail?: string
}

export default function PlaygroundPage() {
  const { token } = useAuth()
  const { models, loading: catalogLoading, error: catalogError } = useCatalog()
  const [model, setModel] = useState<ModelCatalogItem | null>(null)
  const [systemPrompt, setSystemPrompt] = useState('')
  const [prompt, setPrompt] = useState('')
  const [temperature, setTemperature] = useState(0.7)
  const [maxTokens, setMaxTokens] = useState(1024)
  const [busy, setBusy] = useState(false)
  const [response, setResponse] = useState<ChatResponse | null>(null)
  const [error, setError] = useState('')

  useMemo(() => {
    if (models.length > 0 && !model) setModel(models[0])
  }, [models, model])

  const requestBody = useMemo(() => {
    const messages = []
    if (systemPrompt.trim()) messages.push({ role: 'system', content: systemPrompt.trim() })
    messages.push({ role: 'user', content: prompt.trim() || '...' })
    return {
      model: model?.providerModelId || model?.id || '',
      messages,
      temperature,
      max_tokens: maxTokens,
      stream: false,
    }
  }, [model, systemPrompt, prompt, temperature, maxTokens])

  const curlSnippet = useMemo(
    () =>
      `curl https://api.sanjabai.ir/v1/chat/completions \\\n` +
      `  -H "Authorization: Bearer YOUR_API_KEY" \\\n` +
      `  -H "Content-Type: application/json" \\\n` +
      `  -d '${JSON.stringify(requestBody, null, 2)}'`,
    [requestBody],
  )

  const canSend = model && prompt.trim() && !busy

  const handleSend = async () => {
    if (!canSend) return
    setBusy(true)
    setResponse(null)
    setError('')

    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers,
        body: JSON.stringify(requestBody),
      })
      const data: ChatResponse = await res.json()
      if (!res.ok) {
        throw new Error(data?.error?.message || data?.detail || `خطای سرور: ${res.status}`)
      }
      setResponse(data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'خطا در ارتباط'
      setError(msg)
      toast(msg, 'error')
    } finally {
      setBusy(false)
    }
  }

  const copySnippet = () => {
    navigator.clipboard.writeText(curlSnippet)
    toast('کد کپی شد', 'success')
  }

  const content = response?.choices?.[0]?.message?.content

  return (
    <div className="compare-page">
      <div className="compare-header slide-up">
        <div>
          <h1 className="text-2xl font-bold text-gradient">Playground</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            یک درخواست واقعی به /v1/chat/completions بفرستید و پاسخ خام API را ببینید
          </p>
        </div>
      </div>

      <div className="card space-y-3 slide-up" style={{ animationDelay: '0.05s' }}>
        <div>
          <label className="compare-picker-label">مدل</label>
          {catalogLoading ? (
            <Skeleton className="w-full" height="2.5rem" />
          ) : (
            <ModelPicker models={models} selected={model} onSelect={setModel} loading={false} disabled={busy} />
          )}
        </div>

        <textarea dir="auto"
          className="input w-full"
          rows={2}
          placeholder="system prompt (اختیاری)"
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          disabled={busy}
        />

        <textarea dir="auto"
          className="input w-full"
          rows={4}
          placeholder="prompt خود را بنویسید..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={busy}
        />

        <div className="flex gap-4 flex-wrap items-center">
          <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            temperature
            <input
              type="number" min={0} max={2} step={0.1}
              className="input w-20"
              value={temperature}
              onChange={(e) => setTemperature(Number(e.target.value))}
              disabled={busy}
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            max_tokens
            <input
              type="number" min={1} max={8192} step={1}
              className="input w-24"
              value={maxTokens}
              onChange={(e) => setMaxTokens(Number(e.target.value))}
              disabled={busy}
            />
          </label>
          <button className="btn btn-primary" onClick={handleSend} disabled={!canSend}>
            <Icon name="send" size={16} />
            {busy ? 'در حال ارسال...' : 'ارسال درخواست'}
          </button>
        </div>

        {error && (
          <div className="compare-error-banner">
            <Icon name="close" size={16} />
            <span>{error}</span>
          </div>
        )}
      </div>

      {!catalogLoading && !catalogError && models.length === 0 && (
        <EmptyState icon="playground" title="مدلی در دسترس نیست" description="فهرست مدلها خالی است." />
      )}

      <div className="compare-results">
        <div className="compare-panel slide-up" style={{ animationDelay: '0.1s' }}>
          <div className="compare-panel-header">
            <span className="compare-model-name">پاسخ</span>
          </div>
          <div className="compare-content">
            {busy ? (
              <div className="compare-loading">در حال دریافت پاسخ...</div>
            ) : content ? (
              <MarkdownRenderer content={content} />
            ) : (
              <div className="compare-placeholder">پاسخ مدل در اینجا نمایش داده می‌شود</div>
            )}
          </div>
        </div>

        <div className="compare-panel slide-up" style={{ animationDelay: '0.15s' }}>
          <div className="compare-panel-header">
            <span className="compare-model-name">درخواست (curl)</span>
            <button className="btn btn-ghost" onClick={copySnippet} title="کپی">
              <Icon name="copy" size={16} />
            </button>
          </div>
          <pre className="compare-content" dir="ltr" style={{ overflowX: 'auto', fontSize: '0.8rem' }}>
            {curlSnippet}
          </pre>
        </div>
      </div>

      {response && (
        <div className="card slide-up">
          <div className="compare-panel-header">
            <span className="compare-model-name">پاسخ خام JSON</span>
          </div>
          <pre dir="ltr" style={{ overflowX: 'auto', fontSize: '0.8rem' }}>
            {JSON.stringify(response, null, 2)}
          </pre>
          {response.usage && (
            <div className="compare-stats mt-2">
              <div className="compare-stat">
                <span className="compare-stat-label">توکن ورودی</span>
                <span className="compare-stat-value">{response.usage.prompt_tokens}</span>
              </div>
              <div className="compare-stat">
                <span className="compare-stat-label">توکن خروجی</span>
                <span className="compare-stat-value">{response.usage.completion_tokens}</span>
              </div>
              <div className="compare-stat">
                <span className="compare-stat-label">مجموع</span>
                <span className="compare-stat-value num">{faNum(response.usage.total_tokens)}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
