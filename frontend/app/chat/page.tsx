'use client'

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useAuth } from '@/lib/auth'
import { useCatalog } from '@/lib/useCatalog'
import { type ModelCatalogItem } from '@/types/catalog'
import { Icon } from '@/components/ui/Icon'
import { Skeleton, EmptyState, toast } from '@/components/ui'

/* ═══════════════════════════════════════════════════════════════════════════
   Multiai Chat — Aurora v2
   Cancel, retry, model picker, cost preview, markdown, keyboard shortcuts.
   Model list is now sourced live from useCatalog() — no static MODELS array.
   ═══════════════════════════════════════════════════════════════════════════ */

type Message = { role: 'user' | 'assistant' | 'system'; content: string; id: string }

/* ── Icon helper (inline SVG for special cases) ──────────────────────── */
function CopyIcon({ size = 12 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
    </svg>
  )
}

function CheckIcon({ size = 12 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  )
}

const PRESETS = [
  { icon: 'code' as const, label: 'کدنویسی', description: 'نوشتن و دیباگ کد', prompt: 'یک تابع در ' },
  { icon: 'chat' as const, label: 'ترجمه', description: 'ترجمه متن به فارسی', prompt: 'متن زیر را به فارسی روان ترجمه کن:\n\n' },
  { icon: 'search' as const, label: 'خلاصهسازی', description: 'خلاصه کردن متن طولانی', prompt: 'متن زیر را خلاصه کن:\n\n' },
  { icon: 'dashboard' as const, label: 'تحلیل', description: 'تحلیل داده‌ها و اطلاعات', prompt: 'دادههای زیر را تحلیل کن:\n\n' },
]

function generateId() { return Date.now().toString(36) + Math.random().toString(36).slice(2) }

export default function ChatPage() {
  const { user, token } = useAuth()
  const { models, loading, error: catalogError } = useCatalog()
  const [messages, setMessages] = useState<Message[]>(() => [
    { id: 'welcome', role: 'assistant', content: 'سلام! به Multiai خوش آمدید. چطور میتوانم کمک کنید؟' }
  ])
  const [model, setModel] = useState<ModelCatalogItem | null>(null)
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const [showPresets, setShowPresets] = useState(true)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  // Track scroll position to show/hide scroll-to-bottom button
  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setShowScrollBtn(distFromBottom > 120)
  }, [])
  // Select the first catalog model once the live catalog is available.
  useEffect(() => {
    if (!model && models.length > 0) setModel(models[0])
  }, [models, model])

  // Surface catalog load failures as a toast (design-system error state).
  useEffect(() => {
    if (catalogError) toast('خطا در دریافت فهرست مدلها', 'error')
  }, [catalogError])

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    setShowScrollBtn(false)
  }, [])

  useEffect(() => { scrollToBottom() }, [messages, scrollToBottom])

  const copyToClipboard = useCallback(async (id: string, content: string) => {
    await navigator.clipboard.writeText(content)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }, [])

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setStreaming(false)
  }, [])

  const retry = useCallback(async (msgIndex: number) => {
    if (!model) return
    const userMsg = messages.slice(0, msgIndex).filter(m => m.role === 'user').pop()
    if (!userMsg) return
    const newMsgs = messages.slice(0, msgIndex)
    setMessages(newMsgs)
    setError('')
    await sendMessage(userMsg.content, newMsgs)
  }, [messages, model])

  const sendMessage = useCallback(async (content: string, existingMsgs?: Message[]) => {
    if (!model) return
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
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          model: model.providerModelId || model.id,
          messages: updated.map(m => ({ role: m.role, content: m.content })),
          stream: true,
        }),
        signal: controller.signal,
      })

      if (!res.ok) {
        let errorBody: any = null
        try { errorBody = await res.json() } catch {}
        const code = errorBody?.error?.code || errorBody?.code || ''
        if (code === 'balance' || res.status === 429) {
          throw new Error('INSUFFICIENT_BALANCE')
        }
        throw new Error(errorBody?.error?.message || errorBody?.detail || `خطای سرور: ${res.status}`)
      }

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
            copy[copy.length - 1] = { ...last, content: 'تولید متوقف شد.' }
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
    if (!input.trim() || streaming || !model) return
    sendMessage(input.trim())
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <div className="chat-page">
      {/* ── Model bar ─────────────────────────────────────── */}
      <div className="chat-model-bar">
        <div className="flex items-center gap-2">
          <Icon name="models" size={18} className="text-[var(--accent)]" />
          {loading ? (
            <Skeleton className="w-40" height="1.25rem" />
          ) : catalogError ? (
            <span className="text-sm text-[var(--danger)] flex items-center gap-1">
              <Icon name="close" size={14} /> خطا در بارگذاری مدلها
            </span>
          ) : models.length === 0 ? (
            <span className="text-sm text-[var(--text-muted)]">مدلی یافت نشد</span>
          ) : (
            <div className="model-select-wrapper" dir="ltr">
              <select
                value={model?.id ?? ''}
                onChange={e => setModel(models.find(m => m.id === e.target.value) || models[0] || null)}
                className="model-select"
                data-testid="model-select"
              >
                {models.map(m => (
                  <option key={m.id} value={m.id}>{m.displayName}</option>
                ))}
              </select>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {model && <span className="badge badge-accent text-[10px]" dir="ltr">{model.provider}</span>}
          {streaming && (
            <button onClick={cancel} className="btn btn-ghost btn-sm text-[var(--danger)]">
              <Icon name="close" size={14} />
              توقف
            </button>
          )}
        </div>
      </div>

      {!loading && !catalogError && models.length === 0 && (
        <EmptyState
          icon="models"
          title="مدلی در دسترس نیست"
          description="در حال حاضر فهرست مدلها خالی است. لطفاً اتصال را بررسی کرده و دوباره تلاش کنید."
        />
      )}

      {/* ── Messages ──────────────────────────────────────── */}
      <div ref={scrollContainerRef} onScroll={handleScroll} className="chat-messages">
        {showPresets && messages.length <= 1 && (
          <div className="chat-presets">
            <h3 className="chat-presets-title">از کجا شروع کنیم؟</h3>
            <div className="chat-presets-grid">
              {PRESETS.map(p => (
                <button
                  key={p.label}
                  onClick={() => sendMessage(p.prompt)}
                  className="chat-preset-card"
                >
                  <div className="chat-preset-icon">
                    <Icon name={p.icon} size={20} />
                  </div>
                  <div className="chat-preset-text">
                    <span className="chat-preset-label">{p.label}</span>
                    <span className="chat-preset-desc">{p.description}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={msg.id} className={`chat-row ${msg.role === 'user' ? 'chat-row-user' : 'chat-row-assistant'}`}>
            {msg.role === 'assistant' && (
              <div className="chat-avatar chat-avatar-ai">
                <Icon name="models" size={16} />
              </div>
            )}
            <div className={`chat-bubble ${msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai'}`}>
              {msg.role === 'assistant' && streaming && i === messages.length - 1 && !msg.content && (
                <div className="chat-typing">
                  <span /><span /><span />
                </div>
              )}
              <div className="chat-bubble-content">{msg.content}</div>
              {msg.role === 'assistant' && msg.content && !streaming && (
                <div className="chat-actions">
                  <button
                    onClick={() => copyToClipboard(msg.id, msg.content)}
                    className="chat-action-btn"
                    title="کپی"
                  >
                    {copiedId === msg.id ? <CheckIcon size={13} /> : <CopyIcon size={13} />}
                    {copiedId === msg.id ? 'کپی شد' : 'کپی'}
                  </button>
                  {i > 0 && (
                    <button onClick={() => retry(i)} className="chat-action-btn" title="تلاش مجدد">
                      <Icon name="refresh" size={13} />
                      تلاش مجدد
                    </button>
                  )}
                </div>
              )}
            </div>
            {msg.role === 'user' && user && (
              <div className="chat-avatar chat-avatar-user">
                {user.email?.[0]?.toUpperCase() || '?'}
              </div>
            )}
          </div>
        ))}

        {error && (
          error === 'INSUFFICIENT_BALANCE' ? (
            <div className="chat-error chat-error-balance" style={{
              background: 'linear-gradient(135deg, rgba(243,156,18,0.12), rgba(231,76,60,0.08))',
              border: '1px solid rgba(243,156,18,0.3)',
              borderRadius: '16px',
              padding: '20px 24px',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
              alignItems: 'center',
              textAlign: 'center',
              margin: '12px 0',
            }}>
              <div style={{ fontSize: '2rem' }}>💳</div>
              <div style={{ fontWeight: 700, fontSize: '1.05rem', color: 'var(--text-primary)' }}>
                اعتبار شما تمام شده!
              </div>
              <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                برای ادامه استفاده از مدل‌های هوش مصنوعی، نیاز به شارژ حساب دارید.
                <br />
                با شارژ حساب می‌تونید بدون محدودیت از تمام مدل‌ها استفاده کنید.
              </div>
              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', justifyContent: 'center' }}>
                <a href="/pricing" className="btn btn-primary" style={{ textDecoration: 'none', padding: '10px 24px', borderRadius: '10px', fontWeight: 600, fontSize: '0.9rem' }}>
                  🚀 مشاهده پلن‌ها و شارژ حساب
                </a>
                <a href="/wallet" className="btn btn-ghost" style={{ textDecoration: 'none', padding: '10px 20px', borderRadius: '10px', fontWeight: 500, fontSize: '0.9rem' }}>
                  💰 کیف پول
                </a>
              </div>
            </div>
          ) : (
            <div className="chat-error">
              <Icon name="close" size={14} />
              {error}
            </div>
          )
        )}

        <div ref={bottomRef} />
      </div>

      {/* ── Scroll to bottom ─────────────────────────────── */}
      {showScrollBtn && (
        <button onClick={scrollToBottom} className="chat-scroll-btn" aria-label="اسکرول به پایین">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>
      )}

      {/* ── Composer ──────────────────────────────────────── */}
      <form onSubmit={handleSubmit} className="chat-composer">
        <div className="chat-composer-box">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="پیام خود را بنویسید... (Shift+Enter برای خط جدید)"
            rows={1}
            className="chat-composer-input"
            style={{ fieldSizing: 'content' } as any}
          />
          <button
            type="submit"
            disabled={!input.trim() || streaming || !model}
            className="btn btn-primary btn-icon rounded-xl shrink-0"
            aria-label="ارسال"
          >
            <Icon name="send" size={18} />
          </button>
        </div>
        <div className="chat-composer-footer">
          <span className="chat-composer-status">
            {streaming ? (
              <span className="chat-streaming-dot">در حال تولید...</span>
            ) : (
              `${model?.displayName ?? 'منتظر انتخاب مدل'} — آماده`
            )}
          </span>
          <span className="text-[10px] text-[var(--text-muted)]">
            {input.length > 0 && `${input.length} کاراکتر`}
          </span>
        </div>
      </form>
    </div>
  )
}
