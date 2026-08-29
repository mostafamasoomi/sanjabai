'use client'

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { useCatalog } from '@/lib/useCatalog'
import { tourAnchor } from '@/components/tour/anchors'
import { type ModelCatalogItem } from '@/types/catalog'
import { Icon } from '@/components/ui/Icon'
import { EmptyState, toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { dirFor } from '@/lib/i18n'
import { isUsableModel } from './components/modelUtils'
import ChatMessageItem from './components/ChatMessageItem'
import ConversationSidebar from './components/ConversationSidebar'
import ChatModelBar from './components/ChatModelBar'
import { loadSmartMode, persistSmartMode, type SmartStrategy } from './components/SmartModePopover'
import AssistantBanner from './components/AssistantBanner'
import SearchHintBanner from './components/SearchHintBanner'
import ChatErrorBanner from './components/ChatErrorBanner'
import ChatComposerFooter from './components/ChatComposerFooter'
import { useConversations } from './hooks/useConversations'
import { useChatStream } from './hooks/useChatStream'
import type { Message, UsageStats, Assistant } from './chatTypes'
import { getPresets, makeWelcomeMessage } from './chatHelpers'
import { chatPageStrings } from './page.strings'
import './chat-stream.css'

/* ═══════════════════════════════════════════════════════════════════════════
   Sanjabai Chat — Aurora v2 + Conversation History Sidebar
   Cancel, retry, model picker, cost preview, markdown, keyboard shortcuts.
   Sidebar: conversation CRUD, auto-save, mobile drawer, desktop collapse.
   State/logic is split across hooks/ (conversation CRUD, SSE streaming) and
   components/ (message item, sidebar, model bar, composer footer) -- this
   file wires them together and owns only what's genuinely page-wide.
   ═══════════════════════════════════════════════════════════════════════════ */

export default function ChatPage() {
  const lang = useLang()
  const s = chatPageStrings(lang)
  const { user, token } = useAuth()
  const { models, loading, error: catalogError } = useCatalog()
  const [messages, setMessages] = useState<Message[]>(() => [makeWelcomeMessage(lang)])
  const [model, setModel] = useState<ModelCatalogItem | null>(null);
  const [input, setInput] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [attachedFile, setAttachedFile] = useState<File | null>(null)
  const [webSearch, setWebSearch] = useState<boolean>(() => {
    try { return localStorage.getItem('sanjabai_web_search') === 'true' } catch { return false }
  })
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const [showPresets, setShowPresets] = useState(true)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  // Smart mode is now on/off PLUS a strategy (auto | router | combo:N); both
  // are read and written by SmartModePopover's helpers, which keep the old
  // boolean key untouched so a returning user lands on "auto", not the
  // metered router. smartRunMode is what the backend says actually ran.
  const [smartMode, setSmartMode] = useState<boolean>(() => loadSmartMode().on)
  const [smartStrategy, setSmartStrategy] = useState<SmartStrategy>(() => loadSmartMode().strategy)
  const [smartRunMode, setSmartRunMode] = useState<string | null>(null)
  const [smartModel, setSmartModel] = useState<string | null>(null)
  // SSE-stream-derived state, written by useChatStream (and reset by
  // useConversations on new-chat/switch-conversation) -- owned here rather
  // than inside either hook so both can write it without a circular
  // hook-to-hook dependency; see useChatStream.ts's header comment.
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const [usageStats, setUsageStats] = useState<UsageStats>({ promptTokens: 0, completionTokens: 0, totalTokens: 0, estimatedCost: 0 })
  const [tokensPerSec, setTokensPerSec] = useState<number>(0)
  const [searchHintFor, setSearchHintFor] = useState<{ userMsgId: string; content: string } | null>(null)
  const messagesRef = useRef<Message[]>(messages)

  /* ── Assistant integration ──────────────────────────────────────────── */
  const searchParams = useSearchParams()
  const assistantParam = searchParams?.get('assistant')
  const modelParam = searchParams?.get('model')
  const promptParam = searchParams?.get('prompt')
  const [activeAssistant, setActiveAssistant] = useState<Assistant | null>(null)
  const [loadingAssistant, setLoadingAssistant] = useState(false)

  /* ── Wallet balance ────────────────────────────────────────────────── */
  const [walletBalance, setWalletBalance] = useState<number | null>(null)

  useEffect(() => {
    if (!token) return
    fetch('/api/wallet', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => setWalletBalance(data.balance ?? 0))
      .catch(() => { /* silent */ })
  }, [token])

  const presets = useMemo(() => getPresets(lang), [lang])

  /* ── Pre-send cost estimate ────────────────────────────────────────── */
  const preSendEstimate = useMemo(() => {
    if (!model || !input.trim()) return null
    const estimatedTokens = Math.max(1, Math.round(input.length / 4))
    const costPerMillion = (model.pricing?.inputPerMillion ?? 0)
    const estimatedCost = (estimatedTokens / 1_000_000) * costPerMillion
    return { tokens: estimatedTokens, cost: estimatedCost }
  }, [input, model])

  /* ── Pre-fill input from prompt param ──────────────────────────────── */
  useEffect(() => {
    if (promptParam) {
      setInput(promptParam)
      inputRef.current?.focus()
    }
  }, [promptParam])

  useEffect(() => { messagesRef.current = messages }, [messages])
  useEffect(() => { persistSmartMode(smartMode, smartStrategy) }, [smartMode, smartStrategy])
  useEffect(() => {
    try { localStorage.setItem('sanjabai_web_search', webSearch ? 'true' : 'false') } catch {}
  }, [webSearch])

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

  const conv = useConversations({
    token, models, model, abortRef, setModel,
    setStreaming, setMessages, setShowPresets, setError, setUsageStats, setSmartModel, setSearchHintFor,
  })

  const chat = useChatStream({
    model, models, setModel, token, smartMode, smartStrategy, webSearch, setWebSearch,
    attachedFile, setAttachedFile, activeAssistant, messages, setMessages, setInput, messagesRef,
    activeConversationIdRef: conv.activeConversationIdRef,
    createConversation: conv.createConversation,
    saveMessages: conv.saveMessages,
    setSmartModel, setSmartRunMode, setShowPresets, setWalletBalance, abortRef,
    setStreaming, setError, setUsageStats, setTokensPerSec,
    searchHintFor, setSearchHintFor,
  })

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

  /* ── Model from URL parameter (from /models page) ─────────────────── */
  useEffect(() => {
    if (modelParam && models.length > 0 && !model) {
      const found = models.find(m => m.id === modelParam || m.providerModelId === modelParam)
      // ?model= bypasses the picker, which never offers a down model
      // (ModelPicker filters on isUsableModel). Honour the same gate here so a
      // deep link can't start a chat against a model that guarantees an error;
      // fall back to the default and say so instead of failing silently.
      if (found && isUsableModel(found)) {
        setModel(found)
      } else {
        setModel(models[0])
        toast(found ? s.modelUnavailablePickedDefault : s.modelNotFoundPickedDefault, 'error')
      }
    }
  }, [modelParam, models, model, s])

  // Default-model fallback. MUST NOT fire while a ?model= deep link is being
  // honoured: both this effect and the modelParam effect above run in the same
  // commit phase and both see `model === null`, so without the `!modelParam`
  // guard this one's setModel(models[0]) would be queued *after* the param
  // effect's setModel(found) and win — the user's picked model was silently
  // replaced by the default. The param effect already handles its own fallback
  // (found-but-unusable / not-found both land on models[0] + a toast), so when
  // modelParam is present this effect has nothing left to do.
  useEffect(() => {
    if (!model && models.length > 0 && !modelParam) {
      setModel(models[0]); // Always set the first model as default if no model is selected
    }
  }, [models, model, modelParam]);

  useEffect(() => {
    if (catalogError) toast(s.catalogLoadError, 'error')
  }, [catalogError, s])

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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    chat.sendMessage(input.trim())
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  /* ── Global keyboard shortcuts ─────────────────────────────────────────── */
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      // Ctrl+N: New chat
      if (e.ctrlKey && e.key === 'n') {
        e.preventDefault()
        conv.startNewChat()
        inputRef.current?.focus()
        return
      }
      // Escape: Cancel streaming or close picker
      if (e.key === 'Escape') {
        if (streaming) {
          e.preventDefault()
          chat.cancel()
          return
        }
        // Focus input if nothing else to escape
        if (document.activeElement !== inputRef.current) {
          inputRef.current?.focus()
        }
      }
    }
    window.addEventListener('keydown', handleGlobalKeyDown)
    return () => window.removeEventListener('keydown', handleGlobalKeyDown)
  }, [streaming, chat, conv])

  const sidebarContent = (
    <ConversationSidebar
      startNewChat={conv.startNewChat}
      sidebarSearchQuery={conv.sidebarSearchQuery}
      setSidebarSearchQuery={conv.setSidebarSearchQuery}
      loadingConversations={conv.loadingConversations}
      conversationsCount={conv.conversations.length}
      filteredConversations={conv.filteredConversations}
      groupedConversations={conv.groupedConversations}
      activeConversationId={conv.activeConversationId}
      loadConversation={conv.loadConversation}
      confirmDeleteId={conv.confirmDeleteId}
      setConfirmDeleteId={conv.setConfirmDeleteId}
      deletingId={conv.deletingId}
      deleteConversation={conv.deleteConversation}
    />
  )

  return (
    <>
      {/* Mobile overlay */}
      {isMobile && conv.mobileDrawerOpen && (
        <div className="conv-drawer-overlay" onClick={() => conv.setMobileDrawerOpen(false)} />
      )}

      <div className={`chat-page ${!isMobile && conv.sidebarOpen ? 'chat-page-with-sidebar' : ''}`}>
        {/* ── Conversation sidebar (desktop) ─────────────────────────── */}
        {!isMobile && conv.sidebarOpen && (
          <aside className="conv-sidebar">
            {sidebarContent}
          </aside>
        )}

        {/* ── Mobile drawer ──────────────────────────────────────────── */}
        {isMobile && (
          <aside className={`conv-drawer ${conv.mobileDrawerOpen ? 'conv-drawer-open' : ''}`}>
            <div className="conv-drawer-header">
              <span className="conv-drawer-title">{s.conversationsDrawerTitle}</span>
              <button onClick={() => conv.setMobileDrawerOpen(false)} className="conv-drawer-close">
                <Icon name="close" size={18} />
              </button>
            </div>
            {sidebarContent}
          </aside>
        )}

        {/* ── Main chat area ─────────────────────────────────────────── */}
        <div className="chat-main-area">
          {/* The application view had no page heading at all, so the document
              outline started at h3 and screen-reader users landed on a route
              with nothing to announce. Visually hidden because the model bar
              below already says which model you are talking to — a second,
              visible title would be noise in a surface this dense. */}
          <h1 className="sr-only">{s.pageHeading}</h1>

          <ChatModelBar
            isMobile={isMobile}
            setMobileDrawerOpen={conv.setMobileDrawerOpen}
            sidebarOpen={conv.sidebarOpen}
            setSidebarOpen={conv.setSidebarOpen}
            catalogError={!!catalogError}
            models={models}
            model={model}
            setModel={setModel}
            loading={loading}
            token={token}
            smartMode={smartMode}
            setSmartMode={setSmartMode}
            smartStrategy={smartStrategy}
            setSmartStrategy={(v) => {
              // Changing the ask invalidates the last answer's "what ran", or a
              // stale mismatch would read as a fallback that never happened.
              setSmartStrategy(v); setSmartRunMode(null)
            }}
            smartRunMode={smartRunMode}
            smartModel={smartModel}
            activeConversationId={conv.activeConversationId}
            exportMenuOpen={conv.exportMenuOpen}
            setExportMenuOpen={conv.setExportMenuOpen}
            exportMenuRef={conv.exportMenuRef}
            exportConversation={conv.exportConversation}
            streaming={streaming}
            cancel={chat.cancel}
          />

          {!loading && !catalogError && models.length === 0 && (
            <EmptyState
              icon="models"
              title={s.noModelsTitle}
              description={s.noModelsDescription}
            />
          )}

          <AssistantBanner activeAssistant={activeAssistant} loadingAssistant={loadingAssistant} />

          {/* ── Messages ────────────────────────────────────────────── */}
          <div ref={scrollContainerRef} onScroll={handleScroll} className="chat-messages">
            {showPresets && messages.length <= 1 && (
              <div className="chat-presets">
                <h2 className="chat-presets-title">{s.presetsTitle}</h2>
                <div className="chat-presets-grid">
                  {presets.map(p => (
                    <button
                      key={p.label}
                      onClick={() => chat.sendMessage(p.prompt)}
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
              <ChatMessageItem
                key={msg.id}
                msg={msg}
                index={i}
                isLast={i === messages.length - 1}
                streaming={streaming}
                userAvatar={user?.email?.[0]?.toUpperCase() || ''}
                copiedId={copiedId}
                onCopy={copyToClipboard}
                onRetry={chat.retry}
                onContinue={chat.handleContinue}
                toolEvents={chat.toolEventsByMessageId[msg.id]}
              />
            ))}

            <ChatErrorBanner error={error} />

            <div ref={bottomRef} />
          </div>

          {/* ── Scroll to bottom ────────────────────────────────────── */}
          {showScrollBtn && (
            <button onClick={scrollToBottom} className="chat-scroll-btn" aria-label={s.scrollToBottom}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
          )}

          <SearchHintBanner
            visible={!!searchHintFor && !webSearch}
            onResend={chat.handleResendWithSearch}
            onDismiss={() => setSearchHintFor(null)}
          />

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
                aria-label={s.attachFile}
                title={s.attachFileHint}
                {...tourAnchor('chat.attach')}
              >
                <Icon name="paperclip" size={18} />
              </button>
              <button
                type="button"
                onClick={() => setWebSearch(!webSearch)}
                className={"btn btn-ghost btn-icon rounded-xl shrink-0" + (webSearch ? " text-[var(--accent)]" : "")}
                aria-label={s.webSearch}
                title={s.webSearch}
                style={webSearch ? { color: 'var(--accent)' } : {}}
              >
                <Icon name="globe" size={18} />
              </button>
              <textarea dir={dirFor(lang)}
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={s.composerPlaceholder}
                rows={1}
                className="chat-composer-input"
                style={{ fieldSizing: 'content' } as React.CSSProperties}
                {...tourAnchor('chat.composer')}
              />
              <button
                type="submit"
                disabled={(!input.trim() && !attachedFile) || streaming || !model}
                className="btn btn-primary btn-icon rounded-xl shrink-0"
                aria-label={s.send}
              >
                <Icon name="send" size={18} />
              </button>
            </div>
            {attachedFile && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 10px', marginTop: '6px', background: 'var(--bg-secondary, rgba(255,255,255,0.05))', borderRadius: '10px', fontSize: '0.82rem' }}>
                <Icon name="paperclip" size={14} />
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{attachedFile.name}</span>
                <button type="button" onClick={() => setAttachedFile(null)} aria-label={s.removeAttachment} style={{ display: 'inline-flex', background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: '2px' }}>
                  <Icon name="close" size={12} />
                </button>
              </div>
            )}
            <ChatComposerFooter
              streaming={streaming}
              model={model}
              smartMode={smartMode}
              preSendEstimate={preSendEstimate}
              usageStats={usageStats}
              tokensPerSec={tokensPerSec}
              walletBalance={walletBalance}
              inputLength={input.length}
            />
          </form>
        </div>
      </div>
    </>
  )
}
