'use client'

import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon, type IconName } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════════════════════ */

type SkillVariable = {
  name: string
  description: string
  type?: string
  default?: string
}

type Skill = {
  id: number
  title: string
  title_fa: string
  description: string
  description_fa: string
  category: string
  prompt_template: string
  variables: SkillVariable[]
  default_model: string
  is_public: boolean
  is_featured: boolean
  usage_count: number
  rating_sum: number
  rating_count: number
  tags: string[]
  user_id: number
  created_at: string
}

type UseResult = {
  rendered_prompt: string
  model: string
}

/* ═══════════════════════════════════════════════════════════════
   Constants
   ═══════════════════════════════════════════════════════════════ */

const CATEGORIES = [
  { key: 'all', label: 'همه' },
  { key: 'writing', label: 'نوشتن' },
  { key: 'coding', label: 'برنامه‌نویسی' },
  { key: 'analysis', label: 'تحلیل' },
  { key: 'translation', label: 'ترجمه' },
  { key: 'marketing', label: 'بازاریابی' },
  { key: 'other', label: 'سایر' },
]

const SORT_OPTIONS = [
  { key: 'popular', label: 'محبوبترین' },
  { key: 'newest', label: 'جدیدترین' },
  { key: 'top_rated', label: 'بهترین امتیاز' },
]

const CATEGORY_BADGES: Record<string, string> = {
  writing: 'aurora-cap-blue',
  coding: 'aurora-cap-purple',
  analysis: 'aurora-cap-amber',
  translation: 'aurora-cap-cyan',
  marketing: 'aurora-cap-green',
  other: 'aurora-cap-default',
}

const CATEGORY_LABELS: Record<string, string> = {
  writing: 'نوشتن',
  coding: 'برنامه‌نویسی',
  analysis: 'تحلیل',
  translation: 'ترجمه',
  marketing: 'بازاریابی',
  other: 'سایر',
}

/* ═══════════════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════════════ */

function faNumber(n: number): string {
  return n.toLocaleString('fa-IR')
}

function renderStars(rating: number, size = 14) {
  const stars = []
  for (let i = 1; i <= 5; i++) {
    stars.push(
      <Icon
        key={i}
        name="sparkles"
        size={size}
        className={i <= Math.round(rating) ? 'text-[var(--warning)]' : 'text-[var(--text-muted)]'}
        style={{ opacity: i <= Math.round(rating) ? 1 : 0.3 }}
      />
    )
  }
  return stars
}

function getAverageRating(s: Skill): number {
  return s.rating_count > 0 ? s.rating_sum / s.rating_count : 0
}

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
   Skill Card
   ═══════════════════════════════════════════════════════════════ */

function SkillCard({ skill, onUse }: { skill: Skill; onUse: (s: Skill) => void }) {
  const avg = getAverageRating(skill)

  return (
    <div
      className="card card-interactive"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.625rem',
        padding: '1.25rem',
        animationDelay: '0ms',
      }}
    >
      {/* Header: category badge + usage */}
      <div className="flex items-center justify-between">
        <span
          className={`badge ${CATEGORY_BADGES[skill.category] || 'aurora-cap-default'}`}
          style={{ fontSize: '0.6875rem' }}
        >
          {CATEGORY_LABELS[skill.category] || skill.category}
        </span>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
          <Icon name="user" size={12} />
          {faNumber(skill.usage_count)} استفاده
        </span>
      </div>

      {/* Title */}
      <h3 style={{ fontSize: '0.9375rem', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.4 }}>
        {skill.title_fa || skill.title}
      </h3>

      {/* Description preview */}
      <p
        style={{
          fontSize: '0.8125rem',
          color: 'var(--text-secondary)',
          lineHeight: 1.6,
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}
      >
        {skill.description_fa || skill.description}
      </p>

      {/* Tags */}
      {skill.tags && skill.tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>
          {skill.tags.slice(0, 4).map((tag) => (
            <span
              key={tag}
              style={{
                fontSize: '0.6875rem',
                padding: '0.125rem 0.5rem',
                borderRadius: 'var(--radius-full)',
                background: 'var(--bg-elevated)',
                color: 'var(--text-muted)',
                border: '1px solid var(--border)',
              }}
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Rating + action */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.25rem' }}>
        <div className="flex items-center gap-1">
          {renderStars(avg, 12)}
          {skill.rating_count > 0 && (
            <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginRight: '0.25rem' }}>
              ({faNumber(skill.rating_count)})
            </span>
          )}
        </div>
        <button
          className="btn btn-primary btn-sm"
          onClick={() => onUse(skill)}
          style={{ fontSize: '0.8125rem', padding: '0.375rem 0.875rem' }}
        >
          <Icon name="send" size={14} />
          استفاده
        </button>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   Use Skill Modal
   ═══════════════════════════════════════════════════════════════ */

function UseSkillModal({
  skill,
  open,
  onClose,
  token,
}: {
  skill: Skill | null
  open: boolean
  onClose: () => void
  token: string | null
}) {
  const [variables, setVariables] = useState<Record<string, string>>({})
  const [model, setModel] = useState(skill?.default_model || '')
  const [result, setResult] = useState<UseResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [userRating, setUserRating] = useState(0)

  useEffect(() => {
    if (skill) {
      setModel(skill.default_model)
      setResult(null)
      setUserRating(0)
      const init: Record<string, string> = {}
      skill.variables?.forEach((v) => {
        init[v.name] = v.default || ''
      })
      setVariables(init)
    }
  }, [skill])

  const handleUse = async () => {
    if (!skill || !token) return
    setLoading(true)
    try {
      const res = await fetch(`/api/skills/${skill.id}/use`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ variables, model }),
      })
      if (res.ok) {
        const data: UseResult = await res.json()
        setResult(data)
      } else {
        toast('خطا در اجرای اسکیل', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleRate = async (rating: number) => {
    if (!skill || !token) return
    try {
      const res = await fetch(`/api/skills/${skill.id}/rate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ rating }),
      })
      if (res.ok) {
        setUserRating(rating)
        toast('امتیاز شما ثبت شد', 'success')
      } else {
        toast('خطا در ثبت امتیاز', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    }
  }

  if (!open || !skill) return null

  return (
    <div role="button" tabIndex={0} className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative bg-[var(--bg-elevated)] border border-[var(--border-strong)] rounded-[var(--radius-xl)] p-6 max-w-lg w-full shadow-xl fade-in overflow-y-auto max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
          <div>
            <h2 style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              {skill.title_fa || skill.title}
            </h2>
            <span
              className={`badge ${CATEGORY_BADGES[skill.category] || 'aurora-cap-default'}`}
              style={{ fontSize: '0.625rem', marginTop: '0.375rem', display: 'inline-block' }}
            >
              {CATEGORY_LABELS[skill.category] || skill.category}
            </span>
          </div>
          <button onClick={onClose} className="btn btn-ghost btn-icon" aria-label="بستن">
            <Icon name="close" size={18} />
          </button>
        </div>

        {/* Description */}
        <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: '1rem' }}>
          {skill.description_fa || skill.description}
        </p>

        {/* Stats */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          <span className="flex items-center gap-1">
            <Icon name="user" size={12} />
            {faNumber(skill.usage_count)} استفاده
          </span>
          <span className="flex items-center gap-1">
            {renderStars(getAverageRating(skill), 12)}
            ({faNumber(skill.rating_count)})
          </span>
        </div>

        {/* Tags */}
        {skill.tags && skill.tags.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem', marginBottom: '1rem' }}>
            {skill.tags.map((tag) => (
              <span
                key={tag}
                style={{
                  fontSize: '0.6875rem',
                  padding: '0.125rem 0.5rem',
                  borderRadius: 'var(--radius-full)',
                  background: 'var(--bg-surface)',
                  color: 'var(--text-muted)',
                  border: '1px solid var(--border)',
                }}
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        <div className="divider" style={{ margin: '1rem 0' }} />

        {/* Model selector */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            مدل
          </label>
          <input
            type="text"
            className="input"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="نام مدل (مثلاً gpt-4)"
            style={{ width: '100%', fontSize: '0.875rem' }}
          />
        </div>

        {/* Variables */}
        {skill.variables && skill.variables.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1rem' }}>
            <label style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              متغیرها
            </label>
            {skill.variables.map((v) => (
              <div key={v.name}>
                <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                  {v.description || v.name}
                </label>
                <input
                  type="text"
                  className="input"
                  value={variables[v.name] || ''}
                  onChange={(e) => setVariables({ ...variables, [v.name]: e.target.value })}
                  placeholder={v.name}
                  style={{ width: '100%', fontSize: '0.875rem' }}
                />
              </div>
            ))}
          </div>
        )}

        {/* Action button */}
        <button
          className="btn btn-primary w-full"
          onClick={handleUse}
          disabled={loading}
          style={{ marginBottom: '1rem' }}
        >
          {loading ? (
            <span className="flex items-center gap-2">
              <span className="animate-spin" style={{ width: '1rem', height: '1rem', border: '2px solid var(--border)', borderTopColor: 'var(--accent)', borderRadius: '50%', display: 'inline-block' }} />
              در حال اجرا...
            </span>
          ) : (
            <>
              <Icon name="send" size={16} />
              اجرا
            </>
          )}
        </button>

        {/* Result */}
        {result && (
          <div
            style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              padding: '1rem',
              marginBottom: '1rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>خروجی</span>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  navigator.clipboard.writeText(result.rendered_prompt)
                  toast('کپی شد', 'success')
                }}
                style={{ fontSize: '0.75rem', padding: '0.125rem 0.5rem' }}
              >
                <Icon name="copy" size={12} />
                کپی
              </button>
            </div>
            <pre
              style={{
                fontSize: '0.8125rem',
                color: 'var(--text-primary)',
                whiteSpace: 'pre-wrap',
                fontFamily: 'var(--font-mono, monospace)',
                lineHeight: 1.6,
                margin: 0,
              }}
            >
              {result.rendered_prompt}
            </pre>
            <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
              مدل: {result.model}
            </div>
          </div>
        )}

        {/* Rating */}
        <div className="flex items-center gap-3">
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>امتیاز شما:</span>
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map((r) => (
              <button
                key={r}
                onClick={() => handleRate(r)}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: '0.125rem',
                  color: r <= userRating ? 'var(--warning)' : 'var(--text-muted)',
                  opacity: r <= userRating ? 1 : 0.4,
                  transition: 'all 0.15s ease',
                }}
                aria-label={`${r} ستاره`}
              >
                <Icon name="sparkles" size={18} />
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   Create Skill Modal
   ═══════════════════════════════════════════════════════════════ */

function CreateSkillModal({
  open,
  onClose,
  token,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  token: string | null
  onCreated: () => void
}) {
  const [titleFa, setTitleFa] = useState('')
  const [descriptionFa, setDescriptionFa] = useState('')
  const [category, setCategory] = useState('writing')
  const [promptTemplate, setPromptTemplate] = useState('')
  const [variables, setVariables] = useState<{ name: string; description: string }[]>([])
  const [defaultModel, setDefaultModel] = useState('')
  const [isPublic, setIsPublic] = useState(true)
  const [tagsInput, setTagsInput] = useState('')
  const [loading, setLoading] = useState(false)

  const addVariable = () => {
    setVariables([...variables, { name: '', description: '' }])
  }

  const removeVariable = (index: number) => {
    setVariables(variables.filter((_, i) => i !== index))
  }

  const updateVariable = (index: number, field: 'name' | 'description', value: string) => {
    const updated = [...variables]
    updated[index][field] = value
    setVariables(updated)
  }

  const handleSubmit = async () => {
    if (!token || !titleFa.trim() || !promptTemplate.trim()) {
      toast('لطفاً فیلدهای ضروری را پر کنید', 'error')
      return
    }

    setLoading(true)
    try {
      const body = {
        title: titleFa,
        title_fa: titleFa,
        description: descriptionFa,
        description_fa: descriptionFa,
        category,
        prompt_template: promptTemplate,
        variables: variables.filter((v) => v.name.trim()),
        default_model: defaultModel,
        is_public: isPublic,
        tags: tagsInput
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
      }

      const res = await fetch('/api/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      })

      if (res.ok) {
        toast('اسکیل با موفقیت ایجاد شد', 'success')
        onCreated()
        onClose()
        // Reset form
        setTitleFa('')
        setDescriptionFa('')
        setCategory('writing')
        setPromptTemplate('')
        setVariables([])
        setDefaultModel('')
        setIsPublic(true)
        setTagsInput('')
      } else {
        toast('خطا در ایجاد اسکیل', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setLoading(false)
    }
  }

  if (!open) return null

  return (
    <div role="button" tabIndex={0} className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative bg-[var(--bg-elevated)] border border-[var(--border-strong)] rounded-[var(--radius-xl)] p-6 max-w-lg w-full shadow-xl fade-in overflow-y-auto max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
          <h2 style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            ایجاد اسکیل جدید
          </h2>
          <button onClick={onClose} className="btn btn-ghost btn-icon" aria-label="بستن">
            <Icon name="close" size={18} />
          </button>
        </div>

        {/* Title */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            عنوان *
          </label>
          <input
            type="text"
            className="input"
            value={titleFa}
            onChange={(e) => setTitleFa(e.target.value)}
            placeholder="عنوان اسکیل را وارد کنید"
            style={{ width: '100%', fontSize: '0.875rem' }}
          />
        </div>

        {/* Description */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            توضیحات
          </label>
          <textarea dir="rtl"
            className="input"
            value={descriptionFa}
            onChange={(e) => setDescriptionFa(e.target.value)}
            placeholder="توضیحات اسکیل را وارد کنید"
            rows={3}
            style={{ width: '100%', fontSize: '0.875rem', resize: 'vertical' }}
          />
        </div>

        {/* Category */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            دسته‌بندی
          </label>
          <select
            className="input"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            style={{ width: '100%', fontSize: '0.875rem' }}
          >
            {CATEGORIES.filter((c) => c.key !== 'all').map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </select>
        </div>

        {/* Prompt Template */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            الگوی پرامپت *
          </label>
          <textarea dir="rtl"
            className="input"
            value={promptTemplate}
            onChange={(e) => setPromptTemplate(e.target.value)}
            placeholder="الگوی پرامپت را وارد کنید. از {{variable_name}} برای متغیرها استفاده کنید."
            rows={5}
            style={{ width: '100%', fontSize: '0.875rem', resize: 'vertical', fontFamily: 'var(--font-mono, monospace)' }}
          />
        </div>

        {/* Variables */}
        <div style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <label style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              متغیرها
            </label>
            <button
              className="btn btn-ghost btn-sm"
              onClick={addVariable}
              style={{ fontSize: '0.75rem', padding: '0.125rem 0.5rem' }}
            >
              <Icon name="plus" size={12} />
              افزودن
            </button>
          </div>
          {variables.map((v, i) => (
            <div key={i} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
              <input
                type="text"
                className="input"
                value={v.name}
                onChange={(e) => updateVariable(i, 'name', e.target.value)}
                placeholder="نام متغیر"
                style={{ flex: 1, fontSize: '0.8125rem' }}
              />
              <input
                type="text"
                className="input"
                value={v.description}
                onChange={(e) => updateVariable(i, 'description', e.target.value)}
                placeholder="توضیحات"
                style={{ flex: 2, fontSize: '0.8125rem' }}
              />
              <button
                className="btn btn-ghost btn-icon"
                onClick={() => removeVariable(i)}
                style={{ color: 'var(--danger)', padding: '0.25rem' }}
                aria-label="حذف متغیر"
              >
                <Icon name="trash" size={14} />
              </button>
            </div>
          ))}
        </div>

        {/* Default Model */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            مدل پیش‌فرض
          </label>
          <input
            type="text"
            className="input"
            value={defaultModel}
            onChange={(e) => setDefaultModel(e.target.value)}
            placeholder="نام مدل (اختیاری)"
            style={{ width: '100%', fontSize: '0.875rem' }}
          />
        </div>

        {/* Tags */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
            برچسب‌ها (با کاما جدا کنید)
          </label>
          <input
            type="text"
            className="input"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            placeholder="برچسب۱, برچسب۲, ..."
            style={{ width: '100%', fontSize: '0.875rem' }}
          />
        </div>

        {/* Public toggle */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
          <button
            onClick={() => setIsPublic(!isPublic)}
            style={{
              width: '2.5rem',
              height: '1.375rem',
              borderRadius: 'var(--radius-full)',
              background: isPublic ? 'var(--accent)' : 'var(--bg-surface)',
              border: `1.5px solid ${isPublic ? 'var(--accent)' : 'var(--border)'}`,
              cursor: 'pointer',
              position: 'relative',
              transition: 'all 0.2s ease',
              padding: 0,
            }}
            aria-label={isPublic ? 'عمومی' : 'خصوصی'}
          >
            <span
              style={{
                position: 'absolute',
                top: '1.5px',
                right: isPublic ? 'auto' : '1.5px',
                left: isPublic ? '1.5px' : 'auto',
                width: '1rem',
                height: '1rem',
                borderRadius: '50%',
                background: 'white',
                transition: 'all 0.2s ease',
              }}
            />
          </button>
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
            {isPublic ? 'عمومی — برای همه قابل مشاهده' : 'خصوصی — فقط برای شما'}
          </span>
        </div>

        {/* Submit */}
        <button
          className="btn btn-primary w-full"
          onClick={handleSubmit}
          disabled={loading || !titleFa.trim() || !promptTemplate.trim()}
        >
          {loading ? (
            <span className="flex items-center gap-2">
              <span className="animate-spin" style={{ width: '1rem', height: '1rem', border: '2px solid var(--border)', borderTopColor: 'var(--accent)', borderRadius: '50%', display: 'inline-block' }} />
              در حال ذخیره...
            </span>
          ) : (
            <>
              <Icon name="check" size={16} />
              ذخیره
            </>
          )}
        </button>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   Main Page
   ═══════════════════════════════════════════════════════════════ */

export default function SkillsPage() {
  const { token, user, loading: authLoading } = useAuth()

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
        toast('خطا در دریافت اسکیل‌ها', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setLoading(false)
    }
  }, [category, sort, search, token])

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
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
            وارد شوید
          </h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            برای استفاده از مارکتپلیس اسکیل‌ها، ابتدا وارد حساب کاربری خود شوید.
          </p>
        </div>
        <a href="/login" className="btn btn-primary">
          <Icon name="profile" size={16} />
          ورود به حساب
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
            <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              مارکتپلیس اسکیل‌ها
            </h1>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              اسکیل‌های آماده رو کشف کن و استفاده کن
            </p>
          </div>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setShowCreateModal(true)}
          style={{ fontSize: '0.875rem' }}
        >
          <Icon name="plus" size={16} />
          ایجاد اسکیل جدید
        </button>
      </div>

      {/* ── Search + Sort ── */}
      <div className="flex gap-3 items-center flex-wrap">
        <div style={{ position: 'relative', flex: 1, minWidth: '200px' }}>
          <Icon name="search" size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
          <input
            type="text"
            className="input"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="جستجوی اسکیل..."
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
              aria-label="پاک کردن"
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
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.key} value={opt.key}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* ── Category Tabs ── */}
      <div style={{ display: 'flex', gap: '0.5rem', overflowX: 'auto', paddingBottom: '0.25rem' }}>
        {CATEGORIES.map((cat) => (
          <button
            key={cat.key}
            onClick={() => setCategory(cat.key)}
            className={`btn btn-sm ${category === cat.key ? 'btn-primary' : 'btn-ghost'}`}
            style={{ whiteSpace: 'nowrap', fontSize: '0.8125rem' }}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* ── Results count ── */}
      {!loading && (
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          {faNumber(skills.length)} اسکیل
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
            <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.375rem' }}>
              اسکیلی یافت نشد
            </h3>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              {search.trim()
                ? 'عبارت جستجو را تغییر دهید یا فیلترها را بررسی کنید.'
                : 'هنوز اسکیلی ایجاد نشده است. اولین اسکیل را شما ایجاد کنید!'}
            </p>
          </div>
          <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
            <Icon name="plus" size={16} />
            ایجاد اسکیل جدید
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
