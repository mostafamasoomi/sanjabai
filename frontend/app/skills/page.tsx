'use client'

import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import SkillActivationPanel from './SkillActivationPanel'
import SkillCard from './components/SkillCard'
import UseSkillModal from './components/UseSkillModal'
import CreateSkillModal from './components/CreateSkillModal'
import { type Skill, CATEGORY_KEYS, categoryLabel } from './types'
import { skillsPageStrings } from './page.strings'

/* ═══════════════════════════════════════════════════════════════
   Skeleton
   ═══════════════════════════════════════════════════════════════ */

function CardSkeleton() {
  return (
    <div
      className="card"
      style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}
    >
      <div className="flex items-center gap-2">
        <div className="skeleton" style={{ width: '4rem', height: '1.25rem', borderRadius: 'var(--radius-sm)' }} />
        <div className="skeleton" style={{ width: '3rem', height: '1rem' }} />
      </div>
      <div className="skeleton" style={{ width: '70%', height: '1rem' }} />
      <div className="skeleton" style={{ width: '100%', height: '0.625rem', marginBottom: '0.25rem' }} />
      <div className="skeleton" style={{ width: '85%', height: '0.625rem', marginBottom: '0.25rem' }} />
      <div className="skeleton" style={{ width: '60%', height: '0.625rem' }} />
      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
        <div className="skeleton" style={{ width: '3rem', height: '1.25rem', borderRadius: 'var(--radius-full)' }} />
        <div className="skeleton" style={{ width: '3.5rem', height: '1.25rem', borderRadius: 'var(--radius-full)' }} />
      </div>
      <div className="skeleton" style={{ width: '100%', height: '2rem', borderRadius: 'var(--radius-md)', marginTop: '0.25rem' }} />
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   Main Page
   ═══════════════════════════════════════════════════════════════ */

export default function SkillsPage() {
  const { token, user, loading: authLoading } = useAuth()
  const lang = useLang()
  const s = skillsPageStrings(lang)
  const f = fmt(lang)

  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [category, setCategory] = useState('all')
  const [sort, setSort] = useState('popular')
  const [search, setSearch] = useState('')
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null)
  const [showUseModal, setShowUseModal] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)

  const fetchSkills = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (category !== 'all') params.set('category', category)
      if (sort) params.set('sort', sort)
      if (search.trim()) params.set('q', search.trim())

      const res = await fetch(`/api/skills?${params.toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (res.ok) {
        const data = await res.json()
        // Backend may return array or paginated {items: [...]} format
        setSkills(Array.isArray(data) ? data : (data?.items ?? []))
      } else {
        toast(s.toastFetchError, 'error')
      }
    } catch {
      toast(s.toastServerError, 'error')
    } finally {
      setLoading(false)
    }
  }, [category, sort, search, token, s])

  useEffect(() => {
    fetchSkills()
  }, [fetchSkills])

  const handleUseSkill = (skill: Skill) => {
    setSelectedSkill(skill)
    setShowUseModal(true)
  }

  // Not authenticated state
  if (!authLoading && !user) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', gap: '1.5rem' }}>
        <Icon name="sparkles" size={48} className="text-[var(--text-muted)]" style={{ opacity: 0.4 }} />
        <div className="text-center">
          {/* h1: this branch replaces the whole page, so it owns the outline. */}
          <h1 className="page-title" style={{ marginBottom: '0.5rem' }}>{s.signInTitle}</h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            {s.signInDesc}
          </p>
        </div>
        <a href="/login" className="btn btn-primary">
          <Icon name="profile" size={16} />
          {s.signInAction}
        </a>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {/* ── Header ── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
        <div className="flex items-center gap-3">
          <div
            style={{
              width: '2.5rem',
              height: '2.5rem',
              borderRadius: 'var(--radius-md)',
              background: 'var(--accent-dim)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Icon name="sparkles" size={20} className="text-[var(--accent)]" />
          </div>
          <div>
            <h1 className="page-title">
              {s.pageTitle}
            </h1>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              {s.pageSubtitle}
            </p>
          </div>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setShowCreateModal(true)}
          style={{ fontSize: '0.875rem' }}
        >
          <Icon name="plus" size={16} />
          {s.createNew}
        </button>
      </div>

      <SkillActivationPanel />

      {/* ── Search + Sort ── */}
      <div className="flex gap-3 items-center flex-wrap">
        <div style={{ position: 'relative', flex: 1, minWidth: '200px' }}>
          <Icon name="search" size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
          <input
            type="text"
            className="input"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={s.searchPlaceholder}
            style={{ width: '100%', paddingRight: '2.5rem', fontSize: '0.875rem' }}
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              style={{
                position: 'absolute',
                left: '0.75rem',
                top: '50%',
                transform: 'translateY(-50%)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--text-muted)',
                padding: '0.25rem',
              }}
              aria-label={s.clearAria}
            >
              <Icon name="close" size={14} />
            </button>
          )}
        </div>
        <select
          className="input"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          style={{ fontSize: '0.875rem', minWidth: '140px' }}
        >
          {s.sortOptions.map((opt) => (
            <option key={opt.key} value={opt.key}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* ── Category Tabs ── */}
      <div style={{ display: 'flex', gap: '0.5rem', overflowX: 'auto', paddingBottom: '0.25rem' }}>
        {CATEGORY_KEYS.map((key) => (
          <button
            key={key}
            onClick={() => setCategory(key)}
            className={`btn btn-sm ${category === key ? 'btn-primary' : 'btn-ghost'}`}
            style={{ whiteSpace: 'nowrap', fontSize: '0.8125rem' }}
          >
            {categoryLabel(key, lang)}
          </button>
        ))}
      </div>

      {/* ── Results count ── */}
      {!loading && (
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          {s.resultsCount(f.num(skills.length))}
        </p>
      )}

      {/* ── Loading skeletons ── */}
      {loading && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
            gap: '1rem',
          }}
        >
          {Array.from({ length: 6 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      )}

      {/* ── Empty state ── */}
      {!loading && skills.length === 0 && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '4rem 2rem',
            gap: '1rem',
          }}
        >
          <Icon name="sparkles" size={48} className="text-[var(--text-muted)]" style={{ opacity: 0.4 }} />
          <div className="text-center">
            <h2 className="empty-state__title">{s.emptyTitle}</h2>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              {search.trim() ? s.emptySearchDesc : s.emptyNoneDesc}
            </p>
          </div>
          <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
            <Icon name="plus" size={16} />
            {s.createNew}
          </button>
        </div>
      )}

      {/* ── Skills Grid ── */}
      {!loading && skills.length > 0 && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
            gap: '1rem',
          }}
        >
          {skills.map((skill) => (
            <SkillCard key={skill.id} skill={skill} onUse={handleUseSkill} />
          ))}
        </div>
      )}

      {/* ── Use Skill Modal ── */}
      <UseSkillModal
        skill={selectedSkill}
        open={showUseModal}
        onClose={() => {
          setShowUseModal(false)
          setSelectedSkill(null)
        }}
        token={token}
      />

      {/* ── Create Skill Modal ── */}
      <CreateSkillModal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        token={token}
        onCreated={fetchSkills}
      />
    </div>
  )
}
