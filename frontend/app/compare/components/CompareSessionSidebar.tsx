import { Icon } from '@/components/ui/Icon'
import { Skeleton } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { formatDate } from '@/app/chat/chatHelpers'
import { compareSessionSidebarStrings } from './CompareSessionSidebar.strings'
import type { CompareSessionSummary } from '../hooks/useCompareSessions'

type CompareSessionSidebarProps = {
  startNewComparison: () => void
  loadingSessions: boolean
  sessions: CompareSessionSummary[]
  activeSessionId: number | null
  openSession: (id: number) => void
  confirmDeleteId: number | null
  setConfirmDeleteId: (v: number | null | ((prev: number | null) => number | null)) => void
  deletingId: number | null
  deleteSession: (id: number) => void
}

// Modeled on app/chat/components/ConversationSidebar.tsx (same list/open/
// delete affordances) -- each row shows BOTH model names (this is a
// two-model session, unlike a single-model conversation), see the design
// spec's "history sidebar" note.
export default function CompareSessionSidebar({
  startNewComparison,
  loadingSessions,
  sessions,
  activeSessionId,
  openSession,
  confirmDeleteId,
  setConfirmDeleteId,
  deletingId,
  deleteSession,
}: CompareSessionSidebarProps) {
  const lang = useLang()
  const s = compareSessionSidebarStrings(lang)
  return (
    <div className="conv-sidebar-content">
      <button onClick={startNewComparison} className="conv-new-chat-btn">
        <Icon name="plus" size={16} />
        {s.newComparison}
      </button>

      <div className="conv-list">
        {loadingSessions && sessions.length === 0 ? (
          <div className="conv-list-loading">
            <Skeleton className="w-full" height="2.5rem" />
            <Skeleton className="w-full" height="2.5rem" />
            <Skeleton className="w-full" height="2.5rem" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="conv-list-empty">
            <Icon name="compare" size={20} className="text-[var(--text-muted)]" />
            <span>{s.noSessionsYet}</span>
          </div>
        ) : (
          sessions.map(sess => (
            <div
              key={sess.id}
              className={`conv-item ${activeSessionId === sess.id ? 'conv-item-active' : ''}`}
              onClick={() => openSession(sess.id)}
            >
              <div className="conv-item-content">
                <span className="conv-item-title">{sess.title || s.untitled}</span>
                <span className="conv-item-meta">
                  <span className="compare-picker-badge" style={{ fontSize: '0.6rem', padding: '0.05rem 0.35rem' }}>A</span>
                  <span className="conv-item-model" dir="ltr">{sess.model_a_requested}</span>
                  <span className="compare-picker-badge b" style={{ fontSize: '0.6rem', padding: '0.05rem 0.35rem' }}>B</span>
                  <span className="conv-item-model" dir="ltr">{sess.model_b_requested}</span>
                </span>
                <span className="conv-item-meta">
                  <span className="conv-item-date">{formatDate(sess.updated_at || sess.created_at, lang)}</span>
                </span>
              </div>
              <button
                className="conv-item-delete"
                onClick={(e) => {
                  e.stopPropagation()
                  if (confirmDeleteId === sess.id) {
                    deleteSession(sess.id)
                  } else {
                    setConfirmDeleteId(sess.id)
                    setTimeout(() => setConfirmDeleteId(prev => (prev === sess.id ? null : prev)), 3000)
                  }
                }}
                disabled={deletingId === sess.id}
                title={confirmDeleteId === sess.id ? s.confirmDelete : s.delete}
              >
                {deletingId === sess.id ? (
                  <span className="conv-delete-spin" />
                ) : confirmDeleteId === sess.id ? (
                  <Icon name="check" size={13} />
                ) : (
                  <Icon name="trash" size={13} />
                )}
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
