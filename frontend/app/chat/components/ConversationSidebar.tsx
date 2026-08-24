import { Icon } from '@/components/ui/Icon'
import { Skeleton } from '@/components/ui'
import { CheckIcon, TrashIcon } from './ChatIcons'
import { formatDate } from '../chatHelpers'
import type { Conversation } from '../chatTypes'

type ConversationSidebarProps = {
  startNewChat: () => void
  sidebarSearchQuery: string
  setSidebarSearchQuery: (v: string) => void
  loadingConversations: boolean
  conversationsCount: number
  filteredConversations: Conversation[]
  groupedConversations: [string, Conversation[]][]
  activeConversationId: string | null
  loadConversation: (id: string) => void
  confirmDeleteId: string | null
  setConfirmDeleteId: (v: string | ((prev: string | null) => string | null)) => void
  deletingId: string | null
  deleteConversation: (id: string) => void
}

// Sidebar body shared by the desktop <aside> and the mobile drawer -- see
// ChatPage, which renders this same component in both wrappers.
export default function ConversationSidebar({
  startNewChat,
  sidebarSearchQuery,
  setSidebarSearchQuery,
  loadingConversations,
  conversationsCount,
  filteredConversations,
  groupedConversations,
  activeConversationId,
  loadConversation,
  confirmDeleteId,
  setConfirmDeleteId,
  deletingId,
  deleteConversation,
}: ConversationSidebarProps) {
  return (
    <div className="conv-sidebar-content">
      {/* New chat button */}
      <button onClick={startNewChat} className="conv-new-chat-btn">
        <Icon name="plus" size={16} />
        چت جدید
      </button>

      {/* Search input */}
      <div className="conv-search-wrapper">
        <span className="conv-search-icon"><Icon name="search" size={14} /></span>
        <input
          type="text"
          className="conv-search-input"
          placeholder="جستجوی مکالمه..."
          value={sidebarSearchQuery}
          onChange={e => setSidebarSearchQuery(e.target.value)}
          dir="rtl"
        />
        {sidebarSearchQuery && (
          <button
            className="conv-search-clear"
            onClick={() => setSidebarSearchQuery('')}
            aria-label="پاک کردن جستجو"
          >
            <Icon name="close" size={12} />
          </button>
        )}
      </div>

      {/* Conversation list */}
      <div className="conv-list">
        {loadingConversations && conversationsCount === 0 ? (
          <div className="conv-list-loading">
            <Skeleton className="w-full" height="2.5rem" />
            <Skeleton className="w-full" height="2.5rem" />
            <Skeleton className="w-full" height="2.5rem" />
          </div>
        ) : filteredConversations.length === 0 ? (
          <div className="conv-list-empty">
            <Icon name={sidebarSearchQuery ? 'search' : 'chat'} size={20} className="text-[var(--text-muted)]" />
            <span>{sidebarSearchQuery ? 'مکالمه‌ای یافت نشد' : 'هنوز مکالمهای ندارید'}</span>
          </div>
        ) : (
          groupedConversations.map(([group, items]) => (
            <div key={group} className="conv-date-group">
              <div className="conv-date-header">{group}</div>
              {items.map(conv => (
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
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
