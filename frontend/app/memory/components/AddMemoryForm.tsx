'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { categories } from '../memoryTypes'
import { addMemoryFormStrings } from './AddMemoryForm.strings'

/* ═══════════════════════════════════════════════════════════════
   Add-memory button + inline form. Split out of page.tsx verbatim
   -- no behaviour change.
   ═══════════════════════════════════════════════════════════════ */

export function AddMemoryForm({
  showAddForm,
  setShowAddForm,
  newContent,
  setNewContent,
  newCategory,
  setNewCategory,
  newTags,
  setNewTags,
  saving,
  onSave,
}: {
  showAddForm: boolean
  setShowAddForm: (v: boolean) => void
  newContent: string
  setNewContent: (v: string) => void
  newCategory: string
  setNewCategory: (v: string) => void
  newTags: string
  setNewTags: (v: string) => void
  saving: boolean
  onSave: () => void
}) {
  const lang = useLang()
  const s = addMemoryFormStrings(lang)
  const cats = categories(lang)

  return (
    <div style={{ marginBottom: 20 }}>
      {!showAddForm ? (
        <button
          onClick={() => setShowAddForm(true)}
          className="btn btn-primary"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
        >
          <Icon name="plus" size={14} />
          {s.addMemory}
        </button>
      ) : (
        <div
          className="card"
          style={{ borderColor: 'var(--accent)', borderWidth: 1 }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Icon name="sparkles" size={16} className="text-accent" />
              <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
                {s.newMemory}
              </h3>
            </div>
            <button onClick={() => setShowAddForm(false)} className="btn btn-ghost btn-sm" style={{ padding: '2px 6px' }}>
              <Icon name="close" size={14} />
            </button>
          </div>

          <textarea
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            placeholder={s.contentPlaceholder}
            className="input"
            rows={3}
            style={{ width: '100%', resize: 'vertical', marginBottom: 10 }}
          />

          <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
            <select
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              className="input"
              style={{ flex: 1, fontSize: 13 }}
            >
              {cats.filter((c) => c.key).map((c) => (
                <option key={c.key} value={c.key}>{c.label}</option>
              ))}
            </select>

            <input
              value={newTags}
              onChange={(e) => setNewTags(e.target.value)}
              placeholder={s.tagsPlaceholder}
              className="input"
              style={{ flex: 2, fontSize: 13 }}
            />
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={onSave}
              disabled={saving || !newContent.trim()}
              className="btn btn-primary btn-sm"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
            >
              {saving ? (
                <span style={{ width: 14, height: 14, border: '2px solid var(--border)', borderTopColor: 'var(--accent)', borderRadius: '50%', animation: 'spin 0.6s linear infinite', display: 'inline-block' }} />
              ) : (
                <Icon name="check" size={14} />
              )}
              {s.save}
            </button>
            <button onClick={() => setShowAddForm(false)} className="btn btn-ghost btn-sm">
              {s.cancel}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
