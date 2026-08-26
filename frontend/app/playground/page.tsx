'use client'

import { useState, useMemo } from 'react'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { useCatalog } from '@/lib/useCatalog'
import { type ModelCatalogItem } from '@/types/catalog'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { Skeleton, EmptyState, toast } from '@/components/ui'
import MarkdownRenderer from '@/app/chat/components/MarkdownRenderer'
import ModelPicker from '@/app/chat/components/ModelPicker'
import { playgroundPageStrings } from './page.strings'

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
  const lang = useLang()
  const s = playgroundPageStrings(lang)
  const f = fmt(lang)
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
      `curl https://sanjabai.com/v1/chat/completions \\\n` +
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
      // Real backend route — /api/chat does not exist (only /v1/chat/completions,
      // /v1/smart-chat, /v1/chat/with-file; backend/chat.py:303). The curl
      // snippet shown alongside this form already used the right path; the
      // button itself never did.
      const res = await apiFetch('/v1/chat/completions', {
        method: 'POST',
        headers,
        body: JSON.stringify(requestBody),
      })
      const data: ChatResponse = await res.json()
      if (!res.ok) {
        // data?.error?.message / data?.detail are backend-sourced error
        // messages (Persian only for now) -- see the i18n handoff report.
        throw new Error(data?.error?.message || data?.detail || s.serverError(f.num(res.status)))
      }
      setResponse(data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : s.connectionError
      setError(msg)
      toast(msg, 'error')
    } finally {
      setBusy(false)
    }
  }

  const copySnippet = () => {
    navigator.clipboard.writeText(curlSnippet)
    toast(s.copied, 'success')
  }

  const content = response?.choices?.[0]?.message?.content

  return (
    <div className="compare-page">
      <div className="compare-header">
        <div>
          <h1 className="text-2xl font-bold text-gradient">Playground</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            {s.subtitle}
          </p>
        </div>
      </div>

      <div className="card space-y-3">
        <div>
          <label className="compare-picker-label">{s.model}</label>
          {catalogLoading ? (
            <Skeleton className="w-full" height="2.5rem" />
          ) : (
            <ModelPicker models={models} selected={model} onSelect={setModel} loading={false} disabled={busy} />
          )}
        </div>

        <textarea dir="auto"
          className="input w-full"
          rows={2}
          placeholder={s.systemPromptPlaceholder}
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          disabled={busy}
        />

        <textarea dir="auto"
          className="input w-full"
          rows={4}
          placeholder={s.promptPlaceholder}
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
            {busy ? s.sending : s.send}
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
        <EmptyState icon="playground" title={s.noModelsTitle} description={s.noModelsDesc} />
      )}

      <div className="compare-results">
        <div className="compare-panel">
          <div className="compare-panel-header">
            <span className="compare-model-name">{s.response}</span>
          </div>
          <div className="compare-content">
            {busy ? (
              <div className="compare-loading">{s.receiving}</div>
            ) : content ? (
              <MarkdownRenderer content={content} />
            ) : (
              <div className="compare-placeholder">{s.placeholder}</div>
            )}
          </div>
        </div>

        <div className="compare-panel">
          <div className="compare-panel-header">
            <span className="compare-model-name">{s.request}</span>
            <button className="btn btn-ghost" onClick={copySnippet} title={s.copy}>
              <Icon name="copy" size={16} />
            </button>
          </div>
          <pre className="compare-content" dir="ltr" style={{ overflowX: 'auto', fontSize: '0.8rem' }}>
            {curlSnippet}
          </pre>
        </div>
      </div>

      {response && (
        <div className="card">
          <div className="compare-panel-header">
            <span className="compare-model-name">{s.rawJson}</span>
          </div>
          <pre dir="ltr" style={{ overflowX: 'auto', fontSize: '0.8rem' }}>
            {JSON.stringify(response, null, 2)}
          </pre>
          {response.usage && (
            <div className="compare-stats mt-2">
              <div className="compare-stat">
                <span className="compare-stat-label">{s.tokensInput}</span>
                <span className="compare-stat-value num">{f.num(response.usage.prompt_tokens)}</span>
              </div>
              <div className="compare-stat">
                <span className="compare-stat-label">{s.tokensOutput}</span>
                <span className="compare-stat-value num">{f.num(response.usage.completion_tokens)}</span>
              </div>
              <div className="compare-stat">
                <span className="compare-stat-label">{s.tokensTotal}</span>
                <span className="compare-stat-value num">{f.num(response.usage.total_tokens)}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
