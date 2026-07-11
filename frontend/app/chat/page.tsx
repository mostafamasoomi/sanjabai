'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════════════════
   Multiai Chat — Aurora v2
   Cancel, retry, model picker, cost preview, markdown, keyboard shortcuts.
   ═══════════════════════════════════════════════════════════════════════════ */

type Message = { role: 'user' | 'assistant' | 'system'; content: string; id: string }
type Model = { id: string; name: string; provider: string; tier: string }

const MODELS: Model[] = [
  { id: 'kr/gpt-4o', name: 'GPT-4o', provider: 'OpenAI', tier: 'flagship' },
  { id: 'kr/claude-3.5-sonnet', name: 'Claude 3.5 Sonnet', provider: 'Anthropic', tier: 'flagship' },
  { id: 'kr/gemini-2.5-pro', name: 'Gemini 2.5 Pro', provider: 'Google', tier: 'flagship' },
  { id: 'kr/deepseek-chat', name: 'DeepSeek V3', provider: 'DeepSeek', tier: 'mid' },
  { id: 'kr/gpt-4o-mini', name: 'GPT-4o Mini', provider: 'OpenAI', tier: 'mini' },
  { id: 'kr/claude-opus-4', name: 'Claude Opus 4', provider: 'Anthropic', tier: 'flagship' },
  { id: 'kr/llama-3.1-405b', name: 'Llama 3.1 405B', provider: 'Meta', tier: 'mid' },
  { id: 'kr/bynara-auto', name: 'Bynara Auto', provider: 'Bynara', tier: 'mid' },
]

const PRESETS = [
  { icon: 'code' as const, label: 'کدنویسی', prompt: 'یک تابع در ' },
  { icon: 'chat' as const, label: 'ترجمه', prompt: 'متن زیر را به فارسی روان ترجمه کن:\n\n' },
  { icon: 'search' as const, label: 'خلاصه‌سازی', prompt: 'متن زیر را خلاصه کن:\n\n' },
  { icon: 'dashboard' as const, label: 'تحلیل', prompt: 'داده‌های زیر را تحلیل کن:\n\n' },
]

function generateId() { return Date.now().toString(36) + Math.random().toString(36).slice(2) }

export default function ChatPage() {
  const { user } = useAuth()
  const [messages, setMessages] = useState<Message[]>(() => [
    { id: 'welcome', role: 'assistant', content: 'سلام! 👋 به Multiai خوش آمدید. چطور می‌توانم کمک کنم؟' },
  ])
  const [input, setInput] = useState('')
  const [model, setModel] = useState(MODELS[0])
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const [showPresets, setShowPresets] = useState(true)

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => { scrollToBottom() }, [messages, scrollToBottom])

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setStreaming(false)
  }, [])

  const retry = useCallback(async (msgIndex: number) => {
    const userMsg = messages.slice(0, msgIndex).filter(m => m.role === 'user').pop()
    if (!userMsg) return
    const newMsgs = messages.slice(0, msgIndex)
    setMessages(newMsgs)
    setError('')
    await sendMessage(userMsg.content, newMsgs)
  }, [messages])

  const sendMessage = useCallback(async (content: string, existingMsgs?: Message[]) => {
    const msgs = existingMsgs || messages
    const userMsg: Message = { id: generateId(), role: 'user', content }
    const updated = [...msgs, userMsg]
    setMessages(updated)
    setInput('')
    setShowPresets(false)
    setStreaming(true)
    setError('')

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const base = typeof window !== 'undefined'
        ? (process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000')
        : 'http://127.0.0.1:8000'

      const res = await fetch(`${base}/v1/chat/completions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: model.id,
          messages: updated.map(m => ({ role: m.role, content: m.content })),
          stream: true,
        }),
        signal: controller.signal,
      })

      if (!res.ok) throw new Error(`خطای سرور: ${res.status}`)

      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      const assistantId = generateId()
      setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '' }])

      let acc = ''
      while (true) {
        const { value, done } = await reader!.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        for (const line of chunk.split('\n')) {
          const trimmed = line.trim()
          if (!trimmed || !trimmed.startsWith('data:')) continue
          const data = trimmed.slice(5).trim()
          if (data === '[DONE]') continue
          try {
            const obj = JSON.parse(data)
            const delta = obj.choices?.[0]?.delta?.content
            if (delta) {
              acc += delta
              setMessages(prev => {
                const copy = [...prev]
                const idx = copy.findIndex(m => m.id === assistantId)
                if (idx >= 0) copy[idx] = { ...copy[idx], content: acc }
                return copy
              })
            }
          } catch { /* partial chunk */ }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        setMessages(prev => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          if (last?.role === 'assistant' && !last.content.trim()) {
            copy[copy.length - 1] = { ...last, content: '⏹ تولید متوقف شد.' }
          }
          return copy
        })
      } else {
        setError(err.message || 'خطا در ارتباط')
      }
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }, [messages, model])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || streaming) return
    sendMessage(input.trim())
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-var(--topbar-height)-2rem)]">
      {/* ── Model bar ─────────────────────────────────────── */}
      <div className="flex items-center gap-3 pb-3 border-b border-[var(--border)]">
        <div className="flex items-center gap-2">
          <Icon name="models" size={18} className="text-[var(--accent)]" />
          <select
            value={model.id}
            onChange={e => setModel(MODELS.find(m => m.id === e.target.value) || MODELS[0])}
            className="bg-transparent text-sm font-medium text-[var(--text-primary)] border-none outline-none cursor-pointer"
          >
            {MODELS.map(m => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
        </div>
        <span className="badge badge-accent text-[10px]">{model.provider}</span>
        {streaming && (
          <button onClick={cancel} className="btn btn-ghost btn-sm text-[var(--danger)] ml-auto">
            <Icon name="close" size={14} />
            توقف
          </button>
        )}
      </div>

      {/* ── Messages ──────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto py-4 space-y-4">
        {showPresets && messages.length <= 1 && (
          <div className="grid grid-cols-2 gap-2 mb-4">
            {PRESETS.map(p => (
              <button
                key={p.label}
                onClick={() => sendMessage(p.prompt)}
                className="card card-interactive flex items-center gap-2 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              >
                <Icon name={p.icon} size={16} className="text-[var(--accent)]" />
                {p.label}
              </button>
            ))}
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
              msg.role === 'user'
                ? 'bg-[var(--accent)] text-white rounded-br-md'
                : 'bg-[var(--bg-surface)] border border-[var(--border)] text-[var(--text-primary)] rounded-bl-md'
            }`}>
              <div className="whitespace-pre-wrap">{msg.content || (streaming && i === messages.length - 1 ? '...' : '')}</div>
              {msg.role === 'assistant' && msg.content && i > 0 && !streaming && (
                <div className="flex items-center gap-2 mt-2 pt-2 border-t border-[var(--border)]">
                  <button
                    onClick={() => navigator.clipboard.writeText(msg.content)}
                    className="text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors flex items-center gap-1"
                  >
                    <Icon name="copy" size={12} />
                    کپی
                  </button>
                  <button
                    onClick={() => retry(i)}
                    className="text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors flex items-center gap-1"
                  >
                    <Icon name="refresh" size={12} />
                    تلاش مجدد
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}

        {error && (
          <div className="text-center">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--danger)]/10 text-[var(--danger)] text-sm">
              <Icon name="close" size={14} />
              {error}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* ── Composer ──────────────────────────────────────── */}
      <form onSubmit={handleSubmit} className="relative">
        <div className="flex items-end gap-2 p-3 bg-[var(--bg-surface)] border border-[var(--border)] rounded-[var(--radius-xl)] focus-within:border-[var(--accent)] focus-within:shadow-[var(--shadow-glow)] transition-all">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="پیام خود را بنویسید... (Shift+Enter برای خط جدید)"
            rows={1}
            className="flex-1 bg-transparent border-none outline-none text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] resize-none font-[var(--font-sans)] min-h-[24px] max-h-[120px]"
            style={{ fieldSizing: 'content' } as any}
          />
          <button
            type="submit"
            disabled={!input.trim() || streaming}
            className="btn btn-primary btn-icon rounded-xl shrink-0"
            aria-label="ارسال"
          >
            <Icon name="send" size={18} />
          </button>
        </div>
        <div className="flex items-center justify-between mt-2 px-1">
          <span className="text-[10px] text-[var(--text-muted)]">
            {streaming ? 'در حال تولید...' : `${model.name} — آماده`}
          </span>
          <span className="text-[10px] text-[var(--text-muted)]">
            {input.length} کاراکتر
          </span>
        </div>
      </form>
    </div>
  )
}