import { useState, useCallback, useRef } from 'react'
import { apiFetch } from '@/lib/apiFetch'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import type { Memory } from '../memoryTypes'
import { useMemoriesStrings } from './useMemories.strings'

/* ═══════════════════════════════════════════════════════════════
   All memory-page state and CRUD logic: fetch/search/filter, add,
   edit, delete. Split out of page.tsx verbatim -- no behaviour
   change. The auth-gate redirect effect (`router.replace('/login')`)
   stays in page.tsx since it's page-navigation concern, not data
   fetching -- this hook only exposes `fetchMemories` for that effect
   to call.
   ═══════════════════════════════════════════════════════════════ */

export function useMemories(token: string | null) {
  const lang = useLang()
  const s = useMemoriesStrings(lang)

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
    if (!token) return
    try {
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
      } else {
        toast(s.loadError, 'error')
      }
    } catch {
      toast(s.loadError, 'error')
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

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
      toast(s.contentRequired, 'error')
      return
    }
    if (!token) return
    setSaving(true)
    try {
      const r = await apiFetch('/api/memories', {
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
        toast(s.saved, 'success')
        setNewContent('')
        setNewCategory('other')
        setNewTags('')
        setShowAddForm(false)
        fetchMemories(activeCategory || undefined, searchQuery || undefined)
      } else {
        const data = await r.json()
        toast(data.detail || s.saveError, 'error')
      }
    } catch {
      toast(s.connectionError, 'error')
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
    if (editingId === null || !token) return
    try {
      const r = await apiFetch(`/api/memories/${editingId}`, {
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
        toast(s.updated, 'success')
        setEditingId(null)
        fetchMemories(activeCategory || undefined, searchQuery || undefined)
      } else {
        toast(s.updateError, 'error')
      }
    } catch {
      toast(s.connectionError, 'error')
    }
  }

  const cancelEdit = () => setEditingId(null)

  /* ── Delete memory ────────────────────────────────────────── */
  const deleteMemory = async (id: number) => {
    if (!token) return
    try {
      const r = await apiFetch(`/api/memories/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (r.ok) {
        toast(s.deleted, 'success')
        fetchMemories(activeCategory || undefined, searchQuery || undefined)
      } else {
        toast(s.deleteError, 'error')
      }
    } catch {
      toast(s.connectionError, 'error')
    }
  }

  const isEditing = (id: number) => editingId === id

  return {
    memories,
    loading,
    searchQuery,
    activeCategory,
    showAddForm,
    setShowAddForm,
    newContent,
    setNewContent,
    newCategory,
    setNewCategory,
    newTags,
    setNewTags,
    saving,
    editingId,
    editingContent,
    setEditingContent,
    editingCategory,
    setEditingCategory,
    editingTags,
    setEditingTags,
    fetchMemories,
    handleSearch,
    handleCategory,
    addMemory,
    startEdit,
    saveEdit,
    cancelEdit,
    deleteMemory,
    isEditing,
  }
}
