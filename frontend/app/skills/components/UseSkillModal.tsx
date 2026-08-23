'use client'

import { useState, useEffect } from 'react'
import { apiFetch } from '@/lib/apiFetch'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import {
  type Skill,
  type UseResult,
  CATEGORY_BADGES,
  CATEGORY_LABELS,
  renderStars,
  getAverageRating,
} from '../types'

/* ═══════════════════════════════════════════════════════════════
   Use Skill Modal
   ═══════════════════════════════════════════════════════════════ */

export default function UseSkillModal({
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
      const res = await apiFetch(`/api/skills/${skill.id}/use`, {
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
      const res = await apiFetch(`/api/skills/${skill.id}/rate`, {
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
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
            {faNum(skill.usage_count)} استفاده
          </span>
          <span className="flex items-center gap-1">
            {renderStars(getAverageRating(skill), 12)}
            ({faNum(skill.rating_count)})
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
