'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════════════════════ */

type Memory = {
  id: number
  content: string
  category: string
  source: string
  tags: string[]
  created_at: string
  updated_at: string
}

type Category = { key: string; label: string }

const CATEGORIES: Category[] = [
  { key: '', label: 'همه' },
  { key: 'preferences', label: 'ترجیحات' },
  { key: 'projects', label: 'پروژه‌ها' },
  { key: 'skills', label: 'مهارت‌ها' },
  { key: 'personal', label: 'شخصی' },
  { key: 'other', label: 'سایر' },
]

const CATEGORY_MAP: Record<string, string> = {
  '': 'همه',
  preferences: 'ترجیحات',
  projects: 'پروژه‌ها',
  skills: 'مهارت‌ها',
  personal: 'شخصی',
  other: 'سایر',
}

/* ═══════════════════════════════════════════════════════════════
   Page
   ═══════════════════════════════════════════════════════════════ */

export default function MemoryPage() {
  const { user } = useAuth()

  /* ── State ────────────────────────────────────────────────── */
  const [memories, setMemories] = useState<Memory[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [activeCategory, setActiveCategory] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)

  // Add form
  const [newContent, setNewContent] = useState('')
  const [newCategory, setNewCategory] = useState('other')
  const [newTags, setNewTags] = useState('')
  const [saving, setSaving] = useState(false)

  // Edit state
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editingContent, setEditingContent] = useState('')
  const [editingCategory, setEditingCategory] = useState('')
  const [editingTags, setEditingTags] = useState('')

  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  /* ── Fetch memories ───────────────────────────────────────── */
  const fetchMemories = useCallback(async (category?: string, q?: string) => {
    try {
      const token = localStorage.getItem('sanjabai_auth_token')
      if (!token) return

      let url = '/api/memories'
      if (q) {
        url = `/api/memories/search?q=${encodeURIComponent(q)}`
      } else if (category) {
        url = `/api/memories?category=${encodeURIComponent(category)}`
      }

      const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) {
        const data = await r.json()
        setMemories(data)
      }
    } catch {
      toast('خطا در دریافت حافظه', 'error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (user) fetchMemories()
  }, [user, fetchMemories])

  /* ── Search with debounce ─────────────────────────────────── */
  const handleSearch = (value: string) => {
    setSearchQuery(value)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => {
      fetchMemories(activeCategory, value || undefined)
    }, 400)
  }

  /* ── Category filter ──────────────────────────────────────── */
  const handleCategory = (cat: string) => {
    setActiveCategory(cat)
    setSearchQuery('')
    fetchMemories(cat || undefined)
  }

  /* ── Add memory ───────────────────────────────────────────── */
  const addMemory = async () => {
    if (!newContent.trim()) {
      toast('محتوا را وارد کنید', 'error')
      return
    }
    setSaving(true)
    try {
      const token = localStorage.getItem('sanjabai_auth_token')
      const r = await fetch('/api/memories', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          content: newContent.trim(),
          category: newCategory,
          tags: newTags.split(',').map((t) => t.trim()).filter(Boolean),
        }),
      })
      if (r.ok) {
        toast('حافظه ذخیره شد', 'success')
        setNewContent('')
        setNewCategory('other')
        setNewTags('')
        setShowAddForm(false)
        fetchMemories(activeCategory || undefined, searchQuery || undefined)
      } else {
        const data = await r.json()
        toast(data.detail || 'خطا در ذخیره', 'error')
      }
    } catch {
      toast('خطا در ارتباط', 'error')
    } finally {
      setSaving(false)
    }
  }

  /* ── Edit memory ──────────────────────────────────────────── */
  const startEdit = (m: Memory) => {
    setEditingId(m.id)
    setEditingContent(m.content)
    setEditingCategory(m.category)
    setEditingTags(m.tags.join(', '))
  }

  const saveEdit = async () => {
    if (editingId === null) return
    try {
      const token = localStorage.getItem('sanjabai_auth_token')
      const r = await fetch(`/api/memories/${editingId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          content: editingContent.trim(),
          category: editingCategory,
          tags: editingTags.split(',').map((t) => t.trim()).filter(Boolean),
        }),
      })
      if (r.ok) {
        toast('حافظه به‌روزرسانی شد', 'success')
        setEditingId(null)
        fetchMemories(activeCategory || undefined, searchQuery || undefined)
      } else {
        toast('خطا در به‌روزرسانی', 'error')
      }
    } catch {
      toast('خطا در ارتباط', 'error')
    }
  }

  const cancelEdit = () => setEditingId(null)

  /* ── Delete memory ────────────────────────────────────────── */
  const deleteMemory = async (id: number) => {
    try {
      const token = localStorage.getItem('sanjabai_auth_token')
      const r = await fetch(`/api/memories/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (r.ok) {
        toast('حافظه حذف شد', 'success')
        fetchMemories(activeCategory || undefined, searchQuery || undefined)
      } else {
        toast('خطا در حذف', 'error')
      }
    } catch {
      toast('خطا در ارتباط', 'error')
    }
  }

  /* ── Helpers ──────────────────────────────────────────────── */
  const formatDate = (s: string) =>
    new Date(s).toLocaleDateString('fa-IR', { year: 'numeric', month: 'short', day: 'numeric' })

  const isEditing = (id: number) => editingId === id

  /* ── Render ───────────────────────────────────────────────── */
  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '0 16px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: 'var(--radius-lg)',
            background: 'var(--accent-dim)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Icon name="sparkles" size={20} className="text-accent" />
        </div>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.2 }}>
            حافظه هوشمند
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 2 }}>
            اطلاعات و ترجیحات شما برای چت‌های بهتر
          </p>
        </div>
      </div>

      {/* Search bar */}
      <div style={{ position: 'relative', marginBottom: 16 }}>
        <Icon
          name="search"
          size={16}
          style={{
            position: 'absolute',
            right: 12,
            top: '50%',
            transform: 'translateY(-50%)',
            color: 'var(--text-muted)',
          }}
        />
        <input
          value={searchQuery}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="جستجو در حافظه..."
          className="input"
          style={{ width: '100%', paddingRight: 36 }}
        />
        {searchQuery && (
          <button
            onClick={() => handleSearch('')}
            style={{
              position: 'absolute',
              left: 12,
              top: '50%',
              transform: 'translateY(-50%)',
              background: 'none',
              border: 'none',
              padding: 4,
              cursor: 'pointer',
              display: 'flex',
            }}
          >
            <Icon name="close" size={14} className="text-muted" />
          </button>
        )}
      </div>

      {/* Category tabs */}
      <div
        style={{
          display: 'flex',
          gap: 6,
          marginBottom: 20,
          overflowX: 'auto',
          paddingBottom: 4,
        }}
      >
        {CATEGORIES.map((cat) => (
          <button
            key={cat.key}
            onClick={() => handleCategory(cat.key)}
            className={activeCategory === cat.key ? 'btn btn-primary btn-sm' : 'btn btn-ghost btn-sm'}
            style={{
              whiteSpace: 'nowrap',
              fontSize: 13,
              borderRadius: 'var(--radius-md)',
            }}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Add memory button + form */}
      <div style={{ marginBottom: 20 }}>
        {!showAddForm ? (
          <button
            onClick={() => setShowAddForm(true)}
            className="btn btn-primary"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
          >
            <Icon name="plus" size={14} />
            افزودن حافظه
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
                  حافظه جدید
                </h3>
              </div>
              <button onClick={() => setShowAddForm(false)} className="btn btn-ghost btn-sm" style={{ padding: '2px 6px' }}>
                <Icon name="close" size={14} />
              </button>
            </div>

            <textarea dir="rtl"
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              placeholder="محتوای حافظه (مثلاً: زبان برنامه‌نویسی ترجیحی من Python است)"
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
                {CATEGORIES.filter((c) => c.key).map((c) => (
                  <option key={c.key} value={c.key}>{c.label}</option>
                ))}
              </select>

              <input
                value={newTags}
                onChange={(e) => setNewTags(e.target.value)}
                placeholder="برچسب‌ها (با کاما جدا کنید)"
                className="input"
                style={{ flex: 2, fontSize: 13 }}
              />
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={addMemory}
                disabled={saving || !newContent.trim()}
                className="btn btn-primary btn-sm"
                style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
              >
                {saving ? (
                  <span style={{ width: 14, height: 14, border: '2px solid var(--border)', borderTopColor: 'var(--accent)', borderRadius: '50%', animation: 'spin 0.6s linear infinite', display: 'inline-block' }} />
                ) : (
                  <Icon name="check" size={14} />
                )}
                ذخیره
              </button>
              <button onClick={() => setShowAddForm(false)} className="btn btn-ghost btn-sm">
                انصراف
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Info card */}
      <div
        className="card"
        style={{
          marginBottom: 20,
          background: 'var(--accent-dim)',
          borderColor: 'var(--accent)',
          borderWidth: 1,
        }}
      >
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          <Icon name="info" size={16} style={{ color: 'var(--accent)', marginTop: 2, flexShrink: 0 }} />
          <div>
            <h4 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
              حافظه خودکار
            </h4>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              سیستم به‌صورت خودکار اطلاعات مهم شما را از مکالمات استخراج و ذخیره می‌کند.
              این اطلاعات در چت‌های آینده برای ارائه پاسخ‌های شخصی‌تر استفاده می‌شود.
            </p>
          </div>
        </div>
      </div>

      {/* Memory list */}
      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[1, 2, 3].map((i) => (
            <div key={i} className="card">
              <div className="skeleton" style={{ height: 14, width: '70%', marginBottom: 8 }} />
              <div className="skeleton" style={{ height: 10, width: '40%' }} />
            </div>
          ))}
        </div>
      ) : memories.length === 0 ? (
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
            onClick={() => setShowAddForm(true)}
            className="btn btn-primary btn-sm"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
          >
            <Icon name="plus" size={14} />
            افزودن حافظه
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {memories.map((m) => (
            <div key={m.id} className="card" style={{ padding: 16 }}>
              {isEditing(m.id) ? (
                /* Edit mode */
                <div>
                  <textarea dir="rtl"
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
                      {CATEGORIES.filter((c) => c.key).map((c) => (
                        <option key={c.key} value={c.key}>{c.label}</option>
                      ))}
                    </select>
                    <input
                      value={editingTags}
                      onChange={(e) => setEditingTags(e.target.value)}
                      placeholder="برچسب‌ها (با کاما)"
                      className="input"
                      style={{ flex: 2, fontSize: 13 }}
                    />
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={saveEdit} className="btn btn-primary btn-sm" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      <Icon name="check" size={14} />
                      ذخیره
                    </button>
                    <button onClick={cancelEdit} className="btn btn-ghost btn-sm">
                      انصراف
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
                      {CATEGORY_MAP[m.category] || m.category}
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
                      {m.source === 'manual' ? 'دستی' : 'خودکار'}
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
                        {formatDate(m.created_at)}
                      </span>
                      {m.updated_at !== m.created_at && (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                          <Icon name="refresh" size={11} />
                          ویرایش: {formatDate(m.updated_at)}
                        </span>
                      )}
                    </div>

                    <div style={{ display: 'flex', gap: 4 }}>
                      <button
                        onClick={() => startEdit(m)}
                        className="btn btn-ghost btn-sm"
                        title="ویرایش"
                        style={{ padding: '4px 8px' }}
                      >
                        <Icon name="profile" size={14} />
                      </button>
                      <button
                        onClick={() => deleteMemory(m.id)}
                        className="btn btn-ghost btn-sm"
                        title="حذف"
                        style={{ padding: '4px 8px', color: 'var(--danger)' }}
                      >
                        <Icon name="trash" size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Keyframe for spinner */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
