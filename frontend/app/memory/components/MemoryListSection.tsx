import { Icon } from '@/components/ui/Icon'
import { MemoryCard } from './MemoryCard'
import type { Memory } from '../memoryTypes'

/* ═══════════════════════════════════════════════════════════════
   Memory list: loading skeleton, empty state, or the list of cards.
   Split out of page.tsx verbatim -- no behaviour change.
   ═══════════════════════════════════════════════════════════════ */

export function MemoryListSection({
  loading,
  memories,
  onAddClick,
  editingId,
  editingContent,
  setEditingContent,
  editingCategory,
  setEditingCategory,
  editingTags,
  setEditingTags,
  onSaveEdit,
  onCancelEdit,
  onStartEdit,
  onDelete,
}: {
  loading: boolean
  memories: Memory[]
  onAddClick: () => void
  editingId: number | null
  editingContent: string
  setEditingContent: (v: string) => void
  editingCategory: string
  setEditingCategory: (v: string) => void
  editingTags: string
  setEditingTags: (v: string) => void
  onSaveEdit: () => void
  onCancelEdit: () => void
  onStartEdit: (m: Memory) => void
  onDelete: (id: number) => void
}) {
  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {[1, 2, 3].map((i) => (
          <div key={i} className="card">
            <div className="skeleton" style={{ height: 14, width: '70%', marginBottom: 8 }} />
            <div className="skeleton" style={{ height: 10, width: '40%' }} />
          </div>
        ))}
      </div>
    )
  }

  if (memories.length === 0) {
    return (
      <div
        className="card"
        style={{
          textAlign: 'center',
          padding: '48px 24px',
        }}
      >
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: '50%',
            background: 'var(--bg-surface)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 16px',
          }}
        >
          <Icon name="sparkles" size={28} className="text-muted" />
        </div>
        <p style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>
          هنوز حافظه‌ای ذخیره نشده
        </p>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
          اولین حافظه خود را اضافه کنید یا اجازه دهید سیستم به‌صورت خودکار اطلاعات شما را یاد بگیرد.
        </p>
        <button
          onClick={onAddClick}
          className="btn btn-primary btn-sm"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
        >
          <Icon name="plus" size={14} />
          افزودن حافظه
        </button>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {memories.map((m) => (
        <MemoryCard
          key={m.id}
          memory={m}
          isEditing={editingId === m.id}
          editingContent={editingContent}
          setEditingContent={setEditingContent}
          editingCategory={editingCategory}
          setEditingCategory={setEditingCategory}
          editingTags={editingTags}
          setEditingTags={setEditingTags}
          onSaveEdit={onSaveEdit}
          onCancelEdit={onCancelEdit}
          onStartEdit={onStartEdit}
          onDelete={onDelete}
        />
      ))}
    </div>
  )
}
