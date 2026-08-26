'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { categoryMap, categories } from '../memoryTypes'
import type { Memory } from '../memoryTypes'
import { memoryCardStrings } from './MemoryCard.strings'

/* ═══════════════════════════════════════════════════════════════
   A single memory card: view mode, and edit mode. Split out of
   page.tsx verbatim -- no behaviour change.
   ═══════════════════════════════════════════════════════════════ */

export function MemoryCard({
  memory: m,
  isEditing,
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
  memory: Memory
  isEditing: boolean
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
  const lang = useLang()
  const s = memoryCardStrings(lang)
  const f = fmt(lang)
  const catMap = categoryMap(lang)
  const cats = categories(lang)

  return (
    <div className="card" style={{ padding: 16 }}>
      {isEditing ? (
        /* Edit mode */
        <div>
          <textarea
            value={editingContent}
            onChange={(e) => setEditingContent(e.target.value)}
            className="input"
            rows={3}
            style={{ width: '100%', resize: 'vertical', marginBottom: 10 }}
          />
          <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
            <select
              value={editingCategory}
              onChange={(e) => setEditingCategory(e.target.value)}
              className="input"
              style={{ flex: 1, fontSize: 13 }}
            >
              {cats.filter((c) => c.key).map((c) => (
                <option key={c.key} value={c.key}>{c.label}</option>
              ))}
            </select>
            <input
              value={editingTags}
              onChange={(e) => setEditingTags(e.target.value)}
              placeholder={s.tagsPlaceholder}
              className="input"
              style={{ flex: 2, fontSize: 13 }}
            />
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={onSaveEdit} className="btn btn-primary btn-sm" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <Icon name="check" size={14} />
              {s.save}
            </button>
            <button onClick={onCancelEdit} className="btn btn-ghost btn-sm">
              {s.cancel}
            </button>
          </div>
        </div>
      ) : (
        /* View mode */
        <div>
          <p style={{ fontSize: 14, color: 'var(--text-primary)', lineHeight: 1.7, marginBottom: 12 }}>
            {m.content}
          </p>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
            {/* Category badge */}
            <span
              className="badge badge-accent"
              style={{ fontSize: 11, padding: '2px 8px' }}
            >
              {catMap[m.category] || m.category}
            </span>

            {/* Source indicator */}
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                fontSize: 11,
                color: m.source === 'manual' ? 'var(--positive)' : 'var(--text-muted)',
                background: 'var(--bg-surface)',
                padding: '2px 8px',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              <Icon name={m.source === 'manual' ? 'user' : 'sparkles'} size={10} />
              {m.source === 'manual' ? s.manual : s.automatic}
            </span>

            {/* Tags */}
            {m.tags?.map((tag) => (
              <span
                key={tag}
                style={{
                  fontSize: 11,
                  color: 'var(--text-secondary)',
                  background: 'var(--bg-surface)',
                  padding: '2px 8px',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                #{tag}
              </span>
            ))}
          </div>

          <div className="flex items-center justify-between">
            <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-muted)' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <Icon name="calendar" size={11} />
                {f.date(m.created_at)}
              </span>
              {m.updated_at !== m.created_at && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                  <Icon name="refresh" size={11} />
                  {s.edited(f.date(m.updated_at))}
                </span>
              )}
            </div>

            <div style={{ display: 'flex', gap: 4 }}>
              <button
                onClick={() => onStartEdit(m)}
                className="btn btn-ghost btn-sm"
                title={s.edit}
                style={{ padding: '4px 8px' }}
              >
                <Icon name="profile" size={14} />
              </button>
              <button
                onClick={() => onDelete(m.id)}
                className="btn btn-ghost btn-sm"
                title={s.delete}
                style={{ padding: '4px 8px', color: 'var(--danger)' }}
              >
                <Icon name="trash" size={14} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
