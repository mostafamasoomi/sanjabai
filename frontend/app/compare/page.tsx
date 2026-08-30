'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import { useCatalog } from '@/lib/useCatalog'
import { type ModelCatalogItem } from '@/types/catalog'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { Skeleton, EmptyState, toast } from '@/components/ui'
import { usePersistedBoolean } from '@/components/usePersistedBoolean'
import ModelPicker from '@/app/chat/components/ModelPicker'
import { comparePageStrings } from './page.strings'
import { tourAnchor } from '@/components/tour/anchors'
import CompareSessionSidebar from './components/CompareSessionSidebar'
import CompareResultPanel from './components/CompareResultPanel'
import { useCompareSessions } from './hooks/useCompareSessions'
import { useCompareConversation } from './hooks/useCompareConversation'

/* ═══════════════════════════════════════════════════════════════════════════
   Model Compare — Split view side-by-side, with history + continue.
   Pick two models, enter a prompt, see results side by side. Once a
   session exists (first compare's response echoes `session_id`, or a
   history entry was reopened) the same shared composer keeps sending to
   BOTH threads, and one small secondary button under each panel sends
   the same composer text to only that side -- see the design spec at
   docs/superpowers/specs/2026-08-30-compare-history-continue-design.md.

   Kept intentionally thin (JSX + page-local UI state only) -- the
   send/session logic lives in hooks/useCompareConversation.ts and the
   history list/open/delete logic in hooks/useCompareSessions.ts, same
   split app/chat/page.tsx uses over useChatStream.ts/useConversations.ts,
   for the same reason (house 500-line cap per file).
   ═══════════════════════════════════════════════════════════════════════════ */

function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const sz = size === 'sm' ? 16 : size === 'lg' ? 32 : 24
  return (
    <svg className="animate-spin" width={sz} height={sz} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

export default function ComparePage() {
  const { token } = useAuth()
  const lang = useLang()
  const s = comparePageStrings(lang)
  const { models, loading: catalogLoading, error: catalogError } = useCatalog()
  const sessionsHook = useCompareSessions({ token })

  const [modelA, setModelA] = useState<ModelCatalogItem | null>(null)
  const [modelB, setModelB] = useState<ModelCatalogItem | null>(null)

  // Same localStorage key as app/chat/page.tsx so the preference carries
  // across chat and compare.
  const [webSearch, setWebSearch] = useState<boolean>(() => {
    try { return localStorage.getItem('sanjabai_web_search') === 'true' } catch { return false }
  })

  const conv = useCompareConversation({
    models, modelA, modelB, setModelA, setModelB, webSearch,
    openSession: sessionsHook.openSession,
    deleteSession: sessionsHook.deleteSession,
    refetchSessions: sessionsHook.fetchSessions,
  })

  const [sidebarOpen, setSidebarOpen] = usePersistedBoolean('sanjabai_compare_sidebar_open', true)
  // Below 768px, `.conv-sidebar` (styles-chat-sidebar.css) is force-hidden
  // regardless of `sidebarOpen` -- same breakpoint app/chat/page.tsx uses,
  // and the same reason: the desktop sidebar's fixed 280px width doesn't
  // fit. Mirrors chat's isMobile + mobile drawer (`.conv-drawer*` classes,
  // also global) rather than leaving history unreachable on mobile.
  const [isMobile, setIsMobile] = useState(false)
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false)
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768)
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  // Default to first two working models from catalog
  useEffect(() => {
    if (models.length > 0 && !modelA && !modelB) {
      setModelA(models[0])
      if (models.length > 1) setModelB(models[1])
    }
  }, [models, modelA, modelB])

  useEffect(() => {
    if (catalogError) toast(s.fetchModelsError, 'error')
  }, [catalogError, s])

  useEffect(() => {
    try { localStorage.setItem('sanjabai_web_search', webSearch ? 'true' : 'false') } catch {}
  }, [webSearch])

  const startNewComparison = () => {
    conv.startNewComparison()
    setMobileDrawerOpen(false)
  }

  const handleOpenSession = async (id: number) => {
    await conv.handleOpenSession(id)
    setMobileDrawerOpen(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      conv.handleSend('both')
    }
  }

  const sidebarContent = (
    <CompareSessionSidebar
      startNewComparison={startNewComparison}
      loadingSessions={sessionsHook.loadingSessions}
      sessions={sessionsHook.sessions}
      activeSessionId={conv.sessionId}
      openSession={handleOpenSession}
      confirmDeleteId={sessionsHook.confirmDeleteId}
      setConfirmDeleteId={sessionsHook.setConfirmDeleteId}
      deletingId={sessionsHook.deletingId}
      deleteSession={conv.handleDeleteSession}
    />
  )

  return (
    <>
      {/* Mobile drawer overlay -- `.conv-drawer*` (styles-chat-sidebar.css)
          is global, identical mechanism to app/chat/page.tsx's mobile
          conversation drawer. */}
      {isMobile && mobileDrawerOpen && (
        <div className="conv-drawer-overlay" onClick={() => setMobileDrawerOpen(false)} />
      )}
      {isMobile && (
        <aside className={`conv-drawer ${mobileDrawerOpen ? 'conv-drawer-open' : ''}`} aria-label={s.historyAriaLabel}>
          <div className="conv-drawer-header">
            <span className="conv-drawer-title">{s.historyAriaLabel}</span>
            <button onClick={() => setMobileDrawerOpen(false)} className="conv-drawer-close" aria-label={s.closeSidebar}>
              <Icon name="close" size={18} />
            </button>
          </div>
          {sidebarContent}
        </aside>
      )}

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 0 }}>
        {!isMobile && sidebarOpen && (
          <aside
            className="conv-sidebar"
            aria-label={s.historyAriaLabel}
            style={{ height: 'auto', maxHeight: 'calc(100vh - 8rem)', overflowY: 'auto', position: 'sticky', top: '1rem', flexShrink: 0 }}
          >
            {sidebarContent}
          </aside>
        )}

        <div className="compare-page" style={{ flex: 1, minWidth: 0 }}>
          {/* Header */}
          <div className="compare-header">
            <div>
              <h1 className="text-2xl font-bold text-gradient">{s.title}</h1>
              <p className="text-sm text-[var(--text-secondary)] mt-1">
                {s.subtitle}
              </p>
            </div>
            <button
              type="button"
              onClick={() => (isMobile ? setMobileDrawerOpen(true) : setSidebarOpen(prev => !prev))}
              className="conv-toggle-btn"
              title={isMobile || !sidebarOpen ? s.openSidebar : s.closeSidebar}
              aria-label={isMobile || !sidebarOpen ? s.openSidebar : s.closeSidebar}
            >
              <Icon name="history" size={16} />
            </button>
          </div>

          {/* Model pickers + prompt */}
          <div className="card">
            <div className="compare-controls">
              {/* Model A picker */}
              <div className="compare-picker-col">
                <label className="compare-picker-label">
                  <span className="compare-picker-badge a">{s.modelA}</span>
                </label>
                {catalogLoading ? (
                  <Skeleton className="w-full" height="2.5rem" />
                ) : (
                  <ModelPicker
                    models={models.filter(m => m.id !== modelB?.id)}
                    selected={modelA}
                    onSelect={setModelA}
                    loading={false}
                    disabled={conv.busy || conv.sessionId != null}
                  />
                )}
              </div>

              {/* VS divider */}
              <div className="compare-vs">
                <span>{s.vs}</span>
              </div>

              {/* Model B picker */}
              <div className="compare-picker-col">
                <label className="compare-picker-label">
                  <span className="compare-picker-badge b">{s.modelB}</span>
                </label>
                {catalogLoading ? (
                  <Skeleton className="w-full" height="2.5rem" />
                ) : (
                  <ModelPicker
                    models={models.filter(m => m.id !== modelA?.id)}
                    selected={modelB}
                    onSelect={setModelB}
                    loading={false}
                    disabled={conv.busy || conv.sessionId != null}
                  />
                )}
              </div>
            </div>

            {/* Prompt input */}
            <div className="compare-input-row">
              <button
                type="button"
                onClick={() => setWebSearch(!webSearch)}
                className={"btn btn-ghost btn-icon rounded-xl shrink-0" + (webSearch ? " text-[var(--accent)]" : "")}
                aria-label={s.webSearch}
                title={s.webSearch}
                style={webSearch ? { color: 'var(--accent)' } : {}}
                disabled={conv.busy}
              >
                <Icon name="globe" size={18} />
              </button>
              <textarea dir="auto"
                className="input flex-1"
                {...tourAnchor('compare.prompt')}
                rows={2}
                placeholder={conv.sessionId != null ? s.continuePlaceholder : s.promptPlaceholder}
                value={conv.prompt}
                onChange={(e) => conv.setPrompt(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={conv.busy}
              />
              <button
                className="btn btn-primary compare-submit-btn"
                onClick={() => conv.handleSend('both')}
                disabled={!conv.canSend}
              >
                {conv.busy ? (
                  <>
                    <Spinner size="sm" />
                    {s.comparing}
                  </>
                ) : (
                  <>
                    <Icon name="compare" size={16} />
                    {s.compare}
                  </>
                )}
              </button>
            </div>

            {conv.error && (
              <div className="compare-error-banner">
                <Icon name="close" size={16} />
                <span>{conv.error}</span>
              </div>
            )}
          </div>

          {/* Empty state */}
          {!catalogLoading && !catalogError && models.length === 0 && (
            <EmptyState
              icon="compare"
              title={s.noModelsTitle}
              description={s.noModelsDesc}
            />
          )}

          {/* Results — split view */}
          <div className="compare-results">
            <CompareResultPanel
              side="a"
              model={conv.comparedModelA}
              label={conv.labelA}
              thread={conv.threadA}
              isPending={conv.pendingTarget === 'both' || conv.pendingTarget === 'a'}
              sessionActive={conv.sessionId != null}
              canSend={conv.canSend}
              onSendSide={conv.handleSend}
            />
            <CompareResultPanel
              side="b"
              model={conv.comparedModelB}
              label={conv.labelB}
              thread={conv.threadB}
              isPending={conv.pendingTarget === 'both' || conv.pendingTarget === 'b'}
              sessionActive={conv.sessionId != null}
              canSend={conv.canSend}
              onSendSide={conv.handleSend}
            />
          </div>
        </div>
      </div>
    </>
  )
}
