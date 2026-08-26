import { useState, useRef, useCallback, useEffect, type MutableRefObject } from 'react'
import { apiFetch } from '@/lib/apiFetch'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { type ModelCatalogItem } from '@/types/catalog'
import type { Message, UsageStats, Conversation, ConversationDetail } from '../chatTypes'
import { generateId, getDateGroup, makeWelcomeMessage, type DateGroupKey } from '../chatHelpers'
import { useConversationsStrings } from './useConversations.strings'

type UseConversationsParams = {
  token: string | null
  models: ModelCatalogItem[]
  model: ModelCatalogItem | null
  abortRef: MutableRefObject<AbortController | null>
  setModel: (m: ModelCatalogItem) => void
  setStreaming: (v: boolean) => void
  setMessages: (updater: Message[] | ((prev: Message[]) => Message[])) => void
  setShowPresets: (v: boolean) => void
  setError: (v: string) => void
  setUsageStats: (v: UsageStats) => void
  setSmartModel: (v: string | null) => void
  setSearchHintFor: (v: { userMsgId: string; content: string } | null) => void
}

// Everything conversation-sidebar-related: list state, CRUD against
// /api/conversations, date grouping/search filtering, and export. Kept as
// one hook (rather than folded into the page) because it owns state the
// sendMessage SSE loop only *reads* through activeConversationIdRef and
// *calls* through createConversation/saveMessages -- moving it here changes
// nothing about how sendMessage's stream-reading closures behave.
export function useConversations(params: UseConversationsParams) {
  const { token, models, model, abortRef, setModel: _setModel, setStreaming, setMessages, setShowPresets, setError, setUsageStats, setSmartModel, setSearchHintFor } = params
  const lang = useLang()
  const s = useConversationsStrings(lang)

  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [loadingConversations, setLoadingConversations] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [sidebarSearchQuery, setSidebarSearchQuery] = useState('')
  const [exportMenuOpen, setExportMenuOpen] = useState(false)
  const activeConversationIdRef = useRef<string | null>(null)
  const exportMenuRef = useRef<HTMLDivElement>(null)

  useEffect(() => { activeConversationIdRef.current = activeConversationId }, [activeConversationId])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target as Node)) {
        setExportMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

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
        // Backend may return array or paginated {items: [...]} format
        const list = Array.isArray(data) ? data : (data?.items ?? [])
        setConversations(list)
      }
    } catch { /* silent */ }
    finally { setLoadingConversations(false) }
  }, [token, authHeaders])

  useEffect(() => { fetchConversations() }, [fetchConversations])

  const loadConversation = useCallback(async (id: string) => {
    if (!token) return
    // Abort any in-flight stream before swapping conversations: the orphaned
    // stream's setMessages would findIndex into the NEW conversation (-1, text
    // dropped), leave `streaming` stuck true, and keep billing a response the
    // user has navigated away from. Mirrors the Stop button (cancel()).
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
      setStreaming(false)
    }
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
        setMessages([makeWelcomeMessage(lang)])
        setShowPresets(true)
      }
      // Set model from conversation if possible
      if (data.model && models.length > 0) {
        const found = models.find(m => m.providerModelId === data.model || m.id === data.model)
        if (found) _setModel(found)
      }
      setMobileDrawerOpen(false)
    } catch {
      toast(s.loadFailed, 'error')
    }
  }, [token, authHeaders, models, abortRef, setStreaming, setMessages, setShowPresets, _setModel, lang, s])

  const createConversation = useCallback(async (firstUserMsg: string): Promise<string | null> => {
    if (!token) return null
    const title = firstUserMsg.slice(0, 50) + (firstUserMsg.length > 50 ? '...' : '')
    try {
      const res = await apiFetch('/api/conversations', {
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
      await apiFetch(`/api/conversations/${convId}`, {
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
      const res = await apiFetch(`/api/conversations/${id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      })
      if (res.ok) {
        setConversations(prev => prev.filter(c => c.id !== id))
        if (activeConversationId === id) {
          setActiveConversationId(null)
          setMessages([makeWelcomeMessage(lang)])
          setShowPresets(true)
        }
      }
    } catch {
      toast(s.deleteFailed, 'error')
    }
    finally {
      setDeletingId(null)
      setConfirmDeleteId(null)
    }
  }, [token, authHeaders, activeConversationId, setMessages, setShowPresets, lang, s])

  const startNewChat = useCallback(() => {
    // Abort any in-flight stream first — same orphaned-stream hazard as
    // loadConversation (dropped text, stuck composer, silent billing).
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
      setStreaming(false)
    }
    setActiveConversationId(null)
    setMessages([makeWelcomeMessage(lang)])
    setShowPresets(true)
    setError('')
    setMobileDrawerOpen(false)
    setUsageStats({ promptTokens: 0, completionTokens: 0, totalTokens: 0, estimatedCost: 0 })
    setSmartModel(null)
    setSearchHintFor(null)
  }, [abortRef, setStreaming, setMessages, setShowPresets, setError, setUsageStats, setSmartModel, setSearchHintFor, lang])

  /* ── Filtered + grouped conversations ──────────────────────────────────── */
  const filteredConversations = conversations.filter(c => {
    if (!sidebarSearchQuery.trim()) return true
    return c.title.toLowerCase().includes(sidebarSearchQuery.trim().toLowerCase())
  })

  // Keyed by the language-independent DateGroupKey (not the translated
  // label) so this never has to match a string that changed under it when
  // the language toggle flips -- ConversationSidebar renders the label via
  // dateGroupLabel(key, lang).
  const groupedConversations = (() => {
    const groups: Record<DateGroupKey, Conversation[]> = { today: [], yesterday: [], week: [], older: [] }
    for (const c of filteredConversations) {
      const g = getDateGroup(c.updated_at || c.created_at)
      groups[g].push(c)
    }
    return (Object.entries(groups) as [DateGroupKey, Conversation[]][]).filter(([, items]) => items.length > 0)
  })()

  /* ── Export conversation ──────────────────────────────────────────────── */
  const exportConversation = useCallback(async (format: 'json' | 'markdown' | 'text') => {
    if (!token || !activeConversationId) {
      toast(s.selectConversationFirst, 'error')
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
      toast(s.fileDownloaded, 'success')
    } catch {
      toast(s.exportFailed, 'error')
    }
  }, [token, activeConversationId, authHeaders, s])

  return {
    sidebarOpen, setSidebarOpen,
    mobileDrawerOpen, setMobileDrawerOpen,
    conversations,
    activeConversationId, activeConversationIdRef,
    loadingConversations,
    deletingId,
    confirmDeleteId, setConfirmDeleteId,
    sidebarSearchQuery, setSidebarSearchQuery,
    exportMenuOpen, setExportMenuOpen, exportMenuRef,
    filteredConversations,
    groupedConversations,
    loadConversation,
    createConversation,
    saveMessages,
    deleteConversation,
    startNewChat,
    exportConversation,
  }
}
