'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { useMemories } from './hooks/useMemories'
import { MemoryLoginGate } from './components/MemoryLoginGate'
import { MemoryHeader } from './components/MemoryHeader'
import { MemorySearchBar } from './components/MemorySearchBar'
import { CategoryTabs } from './components/CategoryTabs'
import { AddMemoryForm } from './components/AddMemoryForm'
import { MemoryInfoCard } from './components/MemoryInfoCard'
import { MemoryListSection } from './components/MemoryListSection'

/* ═══════════════════════════════════════════════════════════════
   Page

   State/logic is split across hooks/ (fetch/search/add/edit/delete)
   and components/ (header, search bar, category tabs, add form,
   info card, list) -- this file wires them together and owns only
   the auth-gate effect and page-wide layout.
   ═══════════════════════════════════════════════════════════════ */

export default function MemoryPage() {
  const { user, token, loading: authLoading } = useAuth()
  const router = useRouter()

  const {
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
  } = useMemories(token)

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace('/login')
      return
    }
    if (user) fetchMemories()
  }, [user, authLoading, router, fetchMemories])

  /* ── Login gate ───────────────────────────────────────────── */
  if (authLoading || (!user && !authLoading)) {
    return <MemoryLoginGate authLoading={authLoading} />
  }

  /* ── Render ───────────────────────────────────────────────── */
  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '0 16px' }}>
      <MemoryHeader />

      <MemorySearchBar searchQuery={searchQuery} onSearch={handleSearch} />

      <CategoryTabs activeCategory={activeCategory} onSelect={handleCategory} />

      <AddMemoryForm
        showAddForm={showAddForm}
        setShowAddForm={setShowAddForm}
        newContent={newContent}
        setNewContent={setNewContent}
        newCategory={newCategory}
        setNewCategory={setNewCategory}
        newTags={newTags}
        setNewTags={setNewTags}
        saving={saving}
        onSave={addMemory}
      />

      <MemoryInfoCard />

      <MemoryListSection
        loading={loading}
        memories={memories}
        onAddClick={() => setShowAddForm(true)}
        editingId={editingId}
        editingContent={editingContent}
        setEditingContent={setEditingContent}
        editingCategory={editingCategory}
        setEditingCategory={setEditingCategory}
        editingTags={editingTags}
        setEditingTags={setEditingTags}
        onSaveEdit={saveEdit}
        onCancelEdit={cancelEdit}
        onStartEdit={startEdit}
        onDelete={deleteMemory}
      />

      {/* Keyframe for spinner */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
