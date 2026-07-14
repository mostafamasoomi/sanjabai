'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { useCatalog } from '@/lib/useCatalog'
import { type ModelCatalogItem } from '@/types/catalog'
import { Icon } from '@/components/ui/Icon'
import { Skeleton, EmptyState, toast } from '@/components/ui'

/* ═══════════════════════════════════════════════════════════════════════════
   Multiai Chat — Aurora v2 + Conversation History Sidebar
   Cancel, retry, model picker, cost preview, markdown, keyboard shortcuts.
   Sidebar: conversation CRUD, auto-save, mobile drawer, desktop collapse.
   ═══════════════════════════════════════════════════════════════════════════ */

type Message = { role: 'user' | 'assistant' | 'system'; content: string; id: string }

type UsageStats = { promptTokens: number; completionTokens: number; totalTokens: number; estimatedCost: number }

type Conversation = {
  id: string
  title: string
  model: string
  created_at: string
  updated_at: string
}

type ConversationDetail = Conversation & {
  messages: { role: string; content: string }[]
}

type Assistant = {
  id: number
  name: string
  description: string
  system_prompt: string
  model_id: string | null
  icon: string | null
  is_public: boolean
  user_id: number
}

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

function TrashIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
    </svg>
  )
}

const PRESETS = [
  { icon: 'code' as const, label: 'کدنویسی', description: 'نوشتن و دیباگ کد', prompt: 'یک تابع در ' },
  { icon: 'chat' as const, label: 'ترجمه', description: 'ترجمه متن به فارسی', prompt: 'متن زیر را به فارسی روان ترجمه کن:\n\n' },
  { icon: 'search' as const, label: 'خلاصهسازی', description: 'خلاصه کردن متن طولانی', prompt: 'متن زیر را خلاصه کن:\n\n' },
  { icon: 'dashboard' as const, label: 'تحلیل', description: 'تحلیل دادهها و اطلاعات', prompt: 'دادههای زیر را تحلیل کن:\n\n' },
]

function generateId() { return Date.now().toString(36) + Math.random().toString(36).slice(2) }

/* ── Date formatting helper ──────────────────────────────────────────── */
function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return 'اکنون'
    if (diffMins < 60) return `${diffMins} دقیقه پیش`
    if (diffHours < 24) return `${diffHours} ساعت پیش`
    if (diffDays < 7) return `${diffDays} روز پیش`
    return d.toLocaleDateString('fa-IR')
  } catch {
    return ''
  }
}

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
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [attachedFile, setAttachedFile] = useState<File | null>(null)
  const [webSearch, setWebSearch] = useState<boolean>(() => {
    try { return localStorage.getItem('multiai_web_search') === 'true' } catch { return false }
  })
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const [showPresets, setShowPresets] = useState(true)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [smartMode, setSmartMode] = useState<boolean>(() => {
    try { return localStorage.getItem('multiai_smart_mode') === 'true' } catch { return false }
  })
  const [smartModel, setSmartModel] = useState<string | null>(null)
  const [exportMenuOpen, setExportMenuOpen] = useState(false)
  const [usageStats, setUsageStats] = useState<UsageStats>({ promptTokens: 0, completionTokens: 0, totalTokens: 0, estimatedCost: 0 })
  const exportMenuRef = useRef<HTMLDivElement>(null)

  /* ── Assistant integration ──────────────────────────────────────────── */
  const searchParams = useSearchParams()
  const assistantParam = searchParams?.get('assistant')
  const [activeAssistant, setActiveAssistant] = useState<Assistant | null>(null)
  const [loadingAssistant, setLoadingAssistant] = useState(false)

  /* ── Conversation sidebar state ──────────────────────────────────────── */
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [loadingConversations, setLoadingConversations] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const activeConversationIdRef = useRef<string | null>(null)
  const messagesRef = useRef<Message[]>(messages)

  // Keep refs in sync
  useEffect(() => { activeConversationIdRef.current = activeConversationId }, [activeConversationId])
  useEffect(() => { messagesRef.current = messages }, [messages])
  useEffect(() => {
    try { localStorage.setItem('multiai_smart_mode', smartMode ? 'true' : 'false') } catch {}
  }, [smartMode])
  useEffect(() => {
    try { localStorage.setItem('multiai_web_search', webSearch ? 'true' : 'false') } catch {}
  }, [webSearch])
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target as Node)) {
        setExportMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  /* ── Load assistant from URL param ────────────────────────────────── */
  useEffect(() => {
    if (!assistantParam || !token) {
      setActiveAssistant(null)
      return
    }
    let cancelled = false
    setLoadingAssistant(true)
    fetch(`/api/assistants/${assistantParam}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data: Assistant) => {
        if (cancelled) return
        setActiveAssistant(data)
        // Set model from assistant if specified
        if (data.model_id && models.length > 0) {
          const found = models.find(m => m.providerModelId === data.model_id || m.id === data.model_id)
          if (found) setModel(found)
        }
      })
      .catch(() => { if (!cancelled) setActiveAssistant(null) })
      .finally(() => { if (!cancelled) setLoadingAssistant(false) })
    return () => { cancelled = true }
  }, [assistantParam, token, models])

  /* ── Conversation API helpers ────────────────────────────────────────── */
  const authHeaders = useCallback((): Record<string, string> => {
    return token ? { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' }
  }, [token])

  const fetchConversations = useCallback(async () => {
    if (!token) return
    setLoadingConversations(true)
    try {
      const res = await fetch('/api/conversations', { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setConversations(Array.isArray(data) ? data : [])
      }
    } catch { /* silent */ }
    finally { setLoadingConversations(false) }
  }, [token, authHeaders])

  useEffect(() => { fetchConversations() }, [fetchConversations])

  const loadConversation = useCallback(async (id: string) => {
    if (!token) return
    try {
      const res = await fetch(`/api/conversations/${id}`, { headers: authHeaders() })
      if (!res.ok) throw new Error('failed')
      const data: ConversationDetail = await res.json()
      setActiveConversationId(id)
      if (data.messages && data.messages.length > 0) {
        const loaded: Message[] = data.messages.map((m, i) => ({ id: `loaded-${i}`, role: m.role as Message['role'], content: m.content }))
        setMessages(loaded)
        setShowPresets(false)
      } else {
        setMessages([{ id: 'welcome', role: 'assistant', content: 'سلام! به Multiai خوش آمدید. چطور میتوانم کمک کنید؟' }])
        setShowPresets(true)
      }
      // Set model from conversation if possible
      if (data.model && models.length > 0) {
        const found = models.find(m => m.providerModelId === data.model || m.id === data.model)
        if (found) setModel(found)
      }
      setMobileDrawerOpen(false)
    } catch {
      toast('خطا در بارگذاری مکالمه', 'error')
    }
  }, [token, authHeaders, models])

  const createConversation = useCallback(async (firstUserMsg: string): Promise<string | null> => {
    if (!token) return null
    const title = firstUserMsg.slice(0, 50) + (firstUserMsg.length > 50 ? '...' : '')
    try {
      const res = await fetch('/api/conversations', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ title, model: model?.providerModelId || model?.id || '' }),
      })
      if (!res.ok) return null
      const data = await res.json()
      const newConv: Conversation = {
        id: data.id?.toString() || data._id || generateId(),
        title: data.title || title,
        model: data.model || '',
        created_at: data.created_at || new Date().toISOString(),
        updated_at: data.updated_at || new Date().toISOString(),
      }
      setConversations(prev => [newConv, ...prev])
      setActiveConversationId(newConv.id)
      return newConv.id
    } catch { return null }
  }, [token, authHeaders, model])

  const saveMessages = useCallback(async (convId: string, msgs: Message[]) => {
    if (!token) return
    const payload = msgs.filter(m => m.id !== 'welcome').map(m => ({ role: m.role, content: m.content }))
    try {
      await fetch(`/api/conversations/${convId}`, {
        method: 'PUT',
        headers: authHeaders(),
        body: JSON.stringify({ messages: payload }),
      })
    } catch { /* silent - don't interrupt user flow */ }
  }, [token, authHeaders])

  const deleteConversation = useCallback(async (id: string) => {
    if (!token) return
    setDeletingId(id)
    try {
      const res = await fetch(`/api/conversations/${id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      })
      if (res.ok) {
        setConversations(prev => prev.filter(c => c.id !== id))
        if (activeConversationId === id) {
          setActiveConversationId(null)
          setMessages([{ id: 'welcome', role: 'assistant', content: 'سلام! به Multiai خوش آمدید. چطور میتوانم کمک کنید؟' }])
          setShowPresets(true)
        }
      }
    } catch {
      toast('خطا در حذف مکالمه', 'error')
    }
    finally {
      setDeletingId(null)
      setConfirmDeleteId(null)
    }
  }, [token, authHeaders, activeConversationId])

  const startNewChat = useCallback(() => {
    setActiveConversationId(null)
    setMessages([{ id: 'welcome', role: 'assistant', content: 'سلام! به Multiai خوش آمدید. چطور میتوانم کمک کنید؟' }])
    setShowPresets(true)
    setError('')
    setMobileDrawerOpen(false)
    setUsageStats({ promptTokens: 0, completionTokens: 0, totalTokens: 0, estimatedCost: 0 })
    setSmartModel(null)
  }, [])

  /* ── Export conversation ──────────────────────────────────────────────── */
  const exportConversation = useCallback(async (format: 'json' | 'markdown' | 'text') => {
    if (!token || !activeConversationId) {
      toast('ابتدا یک مکالمه را انتخاب کنید', 'error')
      return
    }
    setExportMenuOpen(false)
    try {
      const res = await fetch(`/api/conversations/${activeConversationId}/export?format=${format}`, {
        headers: authHeaders(),
      })
      if (!res.ok) throw new Error('export failed')
      const blob = await res.blob()
      const ext = format === 'markdown' ? 'md' : format
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `conversation-${activeConversationId}.${ext}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      toast('فایل دانلود شد', 'success')
    } catch {
      toast('خطا در خروجی گرفتن', 'error')
    }
  }, [token, activeConversationId, authHeaders])

  /* ── Detect mobile ───────────────────────────────────────────────────── */
  const [isMobile, setIsMobile] = useState(false)
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768)
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  /* ── Existing chat logic ─────────────────────────────────────────────── */
  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setShowScrollBtn(distFromBottom > 120)
  }, [])

  useEffect(() => {
    if (!model && models.length > 0) {
      // 1. Try favorite model from onboarding
      try {
        const favs: string[] = JSON.parse(localStorage.getItem('multiai_favorite_models') || '[]')
        const favModel = models.find(m => favs.includes(m.id))
        if (favModel) { setModel(favModel); return }
      } catch {}
      // 2. Try organisation default model
      fetch('/api/org/default-model')
        .then(r => r.json())
        .then(data => {
          if (data.default_model) {
            const orgModel = models.find(m => m.providerModelId === data.default_model || m.id === data.default_model)
            if (orgModel) { setModel(orgModel); return }
          }
          setModel(models[0])
        })
        .catch(() => setModel(models[0]))
    }
  }, [models, model])

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

  const sendMessageRef = useRef<((content: string, existingMsgs?: Message[]) => Promise<void>) | null>(null)

  const retry = useCallback(async (msgIndex: number) => {
    if (!model) return
    const userMsg = messages.slice(0, msgIndex).filter(m => m.role === 'user').pop()
    if (!userMsg) return
    const newMsgs = messages.slice(0, msgIndex)
    setMessages(newMsgs)
    setError('')
    if (sendMessageRef.current) await sendMessageRef.current(userMsg.content, newMsgs)
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

    // If no active conversation, create one on first user message
    let convId = activeConversationIdRef.current
    if (!convId) {
      convId = await createConversation(content)
    }

    try {
      const chatUrl = (smartMode && !attachedFile) ? '/api/v1/smart-chat' : '/api/chat'
      let res: Response
      if (attachedFile) {
        const fd = new FormData()
        fd.append('file', attachedFile)
        fd.append('model', model.providerModelId || model.id)
        fd.append('messages', JSON.stringify(updated.map(m => ({ role: m.role, content: m.content }))))
        fd.append('stream', 'true')
        const fh: Record<string, string> = {}
        if (token) fh['Authorization'] = `Bearer ${token}`
        res = await fetch('/api/chat/with-file', { method: 'POST', headers: fh, body: fd, signal: controller.signal })
        setAttachedFile(null)
      } else {
        res = await fetch(chatUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            ...(smartMode ? { 'X-Smart-Model': model.providerModelId || model.id } : {}),
          },
          body: JSON.stringify({
            model: model.providerModelId || model.id,
            messages: updated.map(m => ({ role: m.role, content: m.content })),
            stream: true,
            ...(webSearch ? { web_search: true } : {}),
            ...(activeAssistant ? { assistant_id: activeAssistant.id } : {}),
          }),
          signal: controller.signal,
        })
      }

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
      let usageData: any = null
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
            if (obj.usage) usageData = obj.usage
            if (obj.x_smart_model) setSmartModel(obj.x_smart_model)
          } catch { /* partial chunk */ }
        }
      }

      // Auto-save after streaming completes
      if (convId) {
        const finalMsgs = [...updated, { id: assistantId, role: 'assistant' as const, content: acc }]
        saveMessages(convId, finalMsgs)
      }
      // Update usage stats
      if (usageData) {
        const promptTokens = usageData.prompt_tokens || 0
        const completionTokens = usageData.completion_tokens || 0
        const totalTokens = promptTokens + completionTokens
        const estimatedCost = totalTokens * 0.000002 // rough estimate
        setUsageStats(prev => ({
          promptTokens: prev.promptTokens + promptTokens,
          completionTokens: prev.completionTokens + completionTokens,
          totalTokens: prev.totalTokens + totalTokens,
          estimatedCost: prev.estimatedCost + estimatedCost,
        }))
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
      // Save partial progress even on error
      if (convId) {
        saveMessages(convId, messagesRef.current)
      }
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }, [messages, model, token, smartMode, webSearch, createConversation, saveMessages, attachedFile])

  // Keep ref in sync so retry() can call sendMessage without circular deps
  useEffect(() => { sendMessageRef.current = sendMessage }, [sendMessage])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if ((!input.trim() && !attachedFile) || streaming || !model) return
    sendMessage(input.trim())
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  /* ── Sidebar conversation list ───────────────────────────────────────── */
  const sidebarContent = (
    <div className="conv-sidebar-content">
      {/* New chat button */}
      <button onClick={startNewChat} className="conv-new-chat-btn">
        <Icon name="plus" size={16} />
        چت جدید
      </button>

      {/* Conversation list */}
      <div className="conv-list">
        {loadingConversations && conversations.length === 0 ? (
          <div className="conv-list-loading">
            <Skeleton className="w-full" height="2.5rem" />
            <Skeleton className="w-full" height="2.5rem" />
            <Skeleton className="w-full" height="2.5rem" />
          </div>
        ) : conversations.length === 0 ? (
          <div className="conv-list-empty">
            <Icon name="chat" size={20} className="text-[var(--text-muted)]" />
            <span>هنوز مکالمه‌ای ندارید</span>
          </div>
        ) : (
          conversations.map(conv => (
            <div
              key={conv.id}
              className={`conv-item ${activeConversationId === conv.id ? 'conv-item-active' : ''}`}
              onClick={() => loadConversation(conv.id)}
            >
              <div className="conv-item-content">
                <span className="conv-item-title">{conv.title}</span>
                <span className="conv-item-meta">
                  <span className="conv-item-date">{formatDate(conv.updated_at || conv.created_at)}</span>
                  {conv.model && <span className="conv-item-model">{conv.model}</span>}
                </span>
              </div>
              <button
                className="conv-item-delete"
                onClick={(e) => {
                  e.stopPropagation()
                  if (confirmDeleteId === conv.id) {
                    deleteConversation(conv.id)
                  } else {
                    setConfirmDeleteId(conv.id)
                    setTimeout(() => setConfirmDeleteId(prev => prev === conv.id ? null : prev), 3000)
                  }
                }}
                disabled={deletingId === conv.id}
                title={confirmDeleteId === conv.id ? 'برای تأیید دوباره کلیک کنید' : 'حذف'}
              >
                {deletingId === conv.id ? (
                  <span className="conv-delete-spin" />
                ) : confirmDeleteId === conv.id ? (
                  <CheckIcon size={13} />
                ) : (
                  <TrashIcon size={13} />
                )}
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )

  return (
    <>
      {/* Mobile overlay */}
      {isMobile && mobileDrawerOpen && (
        <div className="conv-drawer-overlay" onClick={() => setMobileDrawerOpen(false)} />
      )}

      <div className={`chat-page ${!isMobile && sidebarOpen ? 'chat-page-with-sidebar' : ''}`}>
        {/* ── Conversation sidebar (desktop) ─────────────────────────── */}
        {!isMobile && sidebarOpen && (
          <aside className="conv-sidebar">
            {sidebarContent}
          </aside>
        )}

        {/* ── Mobile drawer ──────────────────────────────────────────── */}
        {isMobile && (
          <aside className={`conv-drawer ${mobileDrawerOpen ? 'conv-drawer-open' : ''}`}>
            <div className="conv-drawer-header">
              <span className="conv-drawer-title">مکالمات</span>
              <button onClick={() => setMobileDrawerOpen(false)} className="conv-drawer-close">
                <Icon name="close" size={18} />
              </button>
            </div>
            {sidebarContent}
          </aside>
        )}

        {/* ── Main chat area ─────────────────────────────────────────── */}
        <div className="chat-main-area">
          {/* ── Model bar ───────────────────────────────────────────── */}
          <div className="chat-model-bar">
            <div className="flex items-center gap-2">
              {/* Sidebar toggle (desktop) / hamburger (mobile) */}
              {isMobile ? (
                <button onClick={() => setMobileDrawerOpen(true)} className="conv-toggle-btn" title="مکالمات">
                  <Icon name="menu" size={18} />
                </button>
              ) : (
                <button onClick={() => setSidebarOpen(prev => !prev)} className="conv-toggle-btn" title={sidebarOpen ? 'بستن سایدبار' : 'باز کردن سایدبار'}>
                  <Icon name={sidebarOpen ? 'close' : 'menu'} size={16} />
                </button>
              )}

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
              {/* Smart Mode toggle */}
              <label className="smart-mode-toggle" title={smartMode ? 'حالت هوشمند فعال' : 'حالت هوشمند غیرفعال'}>
                <input
                  type="checkbox"
                  checked={smartMode}
                  onChange={() => setSmartMode(prev => !prev)}
                  className="sr-only"
                />
                <span className={`smart-mode-switch ${smartMode ? 'smart-mode-on' : ''}`}>
                  <span className="smart-mode-knob" />
                </span>
                <span className="text-xs text-[var(--text-secondary)] select-none">Smart Mode</span>
              </label>
              {smartMode && smartModel && (
                <span className="badge badge-accent text-[9px]" dir="ltr" title="مدل انتخابی توسط Smart Mode">
                  🧠 {smartModel}
                </span>
              )}

              {/* Export dropdown */}
              {activeConversationId && (
                <div className="relative" ref={exportMenuRef}>
                  <button
                    onClick={() => setExportMenuOpen(prev => !prev)}
                    className="conv-toggle-btn"
                    title="خروجی گرفتن"
                  >
                    <Icon name="external" size={16} />
                  </button>
                  {exportMenuOpen && (
                    <div className="export-dropdown">
                      <button className="export-dropdown-item" onClick={() => exportConversation('json')}>
                        <Icon name="code" size={14} /> JSON
                      </button>
                      <button className="export-dropdown-item" onClick={() => exportConversation('markdown')}>
                        <Icon name="chat" size={14} /> Markdown
                      </button>
                      <button className="export-dropdown-item" onClick={() => exportConversation('text')}>
                        <Icon name="info" size={14} /> Text
                      </button>
                    </div>
                  )}
                </div>
              )}

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

          {/* ── Assistant banner ─────────────────────────────────────── */}
          {(activeAssistant || loadingAssistant) && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                padding: '0.75rem 1rem',
                background: 'var(--bg-surface)',
                borderBottom: '1px solid var(--border)',
              }}
            >
              {loadingAssistant ? (
                <div className="skeleton" style={{ width: '100%', height: '1.5rem', borderRadius: 'var(--radius-sm)' }} />
              ) : activeAssistant ? (
                <>
                  <div
                    style={{
                      width: '2rem',
                      height: '2rem',
                      borderRadius: 'var(--radius-md)',
                      background: 'var(--accent)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    <Icon name={(activeAssistant.icon as any) || 'sparkles'} size={16} className="text-white" />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {activeAssistant.name}
                    </div>
                    {activeAssistant.description && (
                      <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {activeAssistant.description}
                      </div>
                    )}
                  </div>
                  <a
                    href={`/assistants/${activeAssistant.id}`}
                    className="btn btn-ghost btn-sm"
                    style={{ fontSize: '0.6875rem', flexShrink: 0 }}
                  >
                    <Icon name="settings" size={12} />
                    تنظیمات
                  </a>
                </>
              ) : null}
            </div>
          )}

          {/* ── Messages ────────────────────────────────────────────── */}
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
                    برای ادامه استفاده از مدلهای هوش مصنوعی، نیاز به شارژ حساب دارید.
                    <br />
                    با شارژ حساب میتونید بدون محدودیت از تمام مدلها استفاده کنید.
                  </div>
                  <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', justifyContent: 'center' }}>
                    <a href="/pricing" className="btn btn-primary" style={{ textDecoration: 'none', padding: '10px 24px', borderRadius: '10px', fontWeight: 600, fontSize: '0.9rem' }}>
                      🚀 مشاهده پلنها و شارژ حساب
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

          {/* ── Scroll to bottom ────────────────────────────────────── */}
          {showScrollBtn && (
            <button onClick={scrollToBottom} className="chat-scroll-btn" aria-label="اسکرول به پایین">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
          )}

          {/* ── Composer ────────────────────────────────────────────── */}
          <form onSubmit={handleSubmit} className="chat-composer">
            <div className="chat-composer-box">
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.md,.csv,.json,.pdf,.text,.log"
                className="hidden"
                onChange={e => { const f = e.target.files?.[0]; if (f) setAttachedFile(f); e.target.value = '' }}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="btn btn-ghost btn-icon rounded-xl shrink-0"
                aria-label="پیوست فایل"
                title="پیوست فایل (txt, md, csv, json, pdf)"
              >
                <Icon name="paperclip" size={18} />
              </button>
              <button
                type="button"
                onClick={() => setWebSearch(!webSearch)}
                className={"btn btn-ghost btn-icon rounded-xl shrink-0" + (webSearch ? " text-[var(--accent)]" : "")}
                aria-label="جستجوی وب"
                title="جستجوی وب"
                style={webSearch ? { color: 'var(--accent, #3b82f6)' } : {}}
              >
                <Icon name="globe" size={18} />
              </button>
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
                disabled={(!input.trim() && !attachedFile) || streaming || !model}
                className="btn btn-primary btn-icon rounded-xl shrink-0"
                aria-label="ارسال"
              >
                <Icon name="send" size={18} />
              </button>
            </div>
            {attachedFile && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 10px', marginTop: '6px', background: 'var(--bg-secondary, rgba(255,255,255,0.05))', borderRadius: '10px', fontSize: '0.82rem' }}>
                <Icon name="paperclip" size={14} />
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{attachedFile.name}</span>
                <button type="button" onClick={() => setAttachedFile(null)} aria-label="حذف پیوست" style={{ display: 'inline-flex', background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: '2px' }}>
                  <Icon name="close" size={12} />
                </button>
              </div>
            )}
            <div className="chat-composer-footer">
              <span className="chat-composer-status">
                {streaming ? (
                  <span className="chat-streaming-dot">در حال تولید...</span>
                ) : (
                  `${model?.displayName ?? 'منتظر انتخاب مدل'} — ${smartMode ? '🧠 Smart Mode' : 'آماده'}`
                )}
              </span>
              {usageStats.totalTokens > 0 && (
                <span className="usage-badge" title={`پرامپت: ${usageStats.promptTokens} | پاسخ: ${usageStats.completionTokens}`}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                  </svg>
                  <span dir="ltr">{usageStats.totalTokens.toLocaleString()} tokens</span>
                  <span className="usage-cost" dir="ltr">~${usageStats.estimatedCost.toFixed(4)}</span>
                </span>
              )}
              <span className="text-[10px] text-[var(--text-muted)]">
                {input.length > 0 && `${input.length} کاراکتر`}
              </span>
            </div>
          </form>
        </div>
      </div>
    </>
  )
}
