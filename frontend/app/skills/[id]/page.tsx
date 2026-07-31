'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'

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
  return faNum(n)
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
   Loading Skeleton
   ═══════════════════════════════════════════════════════════════ */

function DetailSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', padding: '1rem 0' }}>
      <div className="flex gap-2">
        <div className="skeleton" style={{ width: '4rem', height: '1.25rem', borderRadius: 'var(--radius-full)' }} />
        <div className="skeleton" style={{ width: '6rem', height: '1rem' }} />
      </div>
      <div className="skeleton" style={{ width: '60%', height: '1.5rem' }} />
      <div className="skeleton" style={{ width: '100%', height: '0.625rem' }} />
      <div className="skeleton" style={{ width: '85%', height: '0.625rem' }} />
      <div className="skeleton" style={{ width: '70%', height: '0.625rem' }} />
      <div className="divider" />
      <div className="skeleton" style={{ width: '100%', height: '2rem' }} />
      <div className="skeleton" style={{ width: '100%', height: '8rem' }} />
      <div className="skeleton" style={{ width: '100%', height: '2.5rem', borderRadius: 'var(--radius-md)' }} />
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   Skill Detail Page
   ═══════════════════════════════════════════════════════════════ */

export default function SkillDetailPage() {
  const params = useParams()
  const router = useRouter()
  const { token, user, loading: authLoading } = useAuth()

  const skillId = params?.id as string

  const [skill, setSkill] = useState<Skill | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const [variables, setVariables] = useState<Record<string, string>>({})
  const [model, setModel] = useState('')
  const [result, setResult] = useState<UseResult | null>(null)
  const [executing, setExecuting] = useState(false)
  const [userRating, setUserRating] = useState(0)

  const fetchSkill = useCallback(async () => {
    if (!skillId) return
    setLoading(true)
    try {
      const res = await fetch(`/api/skills/${skillId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (res.ok) {
        const data: Skill = await res.json()
        setSkill(data)
        setModel(data.default_model)
        const init: Record<string, string> = {}
        data.variables?.forEach((v) => {
          init[v.name] = v.default || ''
        })
        setVariables(init)
      } else {
        setError(true)
      }
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [skillId, token])

  useEffect(() => {
    fetchSkill()
  }, [fetchSkill])

  const handleUse = async () => {
    if (!skill || !token) return
    setExecuting(true)
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
      setExecuting(false)
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

  const handleShare = () => {
    navigator.clipboard.writeText(window.location.href)
    toast('لینک کپی شد', 'success')
  }

  // Loading state
  if (loading) {
    return (
      <div style={{ maxWidth: '48rem', margin: '0 auto' }}>
        <DetailSkeleton />
      </div>
    )
  }

  // Error state
  if (error || !skill) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '60vh',
          gap: '1.5rem',
        }}
      >
        <Icon name="warning" size={48} className="text-[var(--text-muted)]" style={{ opacity: 0.4 }} />
        <div className="text-center">
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
            اسکیل یافت نشد
          </h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            اسکیل مورد نظر وجود ندارد یا حذف شده است.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => router.push('/skills')}>
          <Icon name="arrowLeft" size={16} />
          بازگشت به مارکتپلیس
        </button>
      </div>
    )
  }

  const avg = getAverageRating(skill)

  return (
    <div style={{ maxWidth: '48rem', margin: '0 auto' }}>
      {/* ── Back button ── */}
      <button
        className="btn btn-ghost btn-sm"
        onClick={() => router.push('/skills')}
        style={{ marginBottom: '1rem', fontSize: '0.8125rem' }}
      >
        <Icon name="arrowLeft" size={14} />
        بازگشت به مارکتپلیس
      </button>

      {/* ── Header ── */}
      <div style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <span
            className={`badge ${CATEGORY_BADGES[skill.category] || 'aurora-cap-default'}`}
            style={{ fontSize: '0.6875rem' }}
          >
            {CATEGORY_LABELS[skill.category] || skill.category}
          </span>
          {skill.is_featured && (
            <span className="badge badge-accent" style={{ fontSize: '0.6875rem' }}>
              <Icon name="sparkles" size={10} />
              ویژه
            </span>
          )}
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginRight: 'auto' }}>
            {new Date(skill.created_at).toLocaleDateString('fa-IR')}
          </span>
        </div>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.4, marginBottom: '0.5rem' }}>
          {skill.title_fa || skill.title}
        </h1>
        <p style={{ fontSize: '0.9375rem', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          {skill.description_fa || skill.description}
        </p>
      </div>

      {/* ── Stats bar ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '1.5rem',
          padding: '1rem',
          background: 'var(--bg-surface)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border)',
          marginBottom: '1.5rem',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
          {renderStars(avg, 16)}
          <span style={{ fontSize: '0.875rem', color: 'var(--text-primary)', fontWeight: 600, marginRight: '0.25rem' }}>
            {avg > 0 ? avg.toFixed(1) : '—'}
          </span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            ({faNumber(skill.rating_count)} نظر)
          </span>
        </div>
        <div style={{ width: '1px', height: '1.25rem', background: 'var(--border)' }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
          <Icon name="user" size={14} />
          {faNumber(skill.usage_count)} استفاده
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
          <Icon name="key" size={14} />
          {skill.default_model || '—'}
        </div>
        <button
          className="btn btn-ghost btn-sm"
          onClick={handleShare}
          style={{ marginRight: 'auto', fontSize: '0.75rem' }}
        >
          <Icon name="link" size={14} />
          اشتراک‌گذاری
        </button>
      </div>

      {/* ── Tags ── */}
      {skill.tags && skill.tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1.5rem' }}>
          {skill.tags.map((tag) => (
            <span
              key={tag}
              style={{
                fontSize: '0.75rem',
                padding: '0.25rem 0.625rem',
                borderRadius: 'var(--radius-full)',
                background: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)',
              }}
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="divider" style={{ margin: '1.5rem 0' }} />

      {/* ── Not authenticated notice ── */}
      {!authLoading && !user && (
        <div
          style={{
            padding: '1.25rem',
            background: 'var(--bg-surface)',
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--border)',
            textAlign: 'center',
            marginBottom: '1.5rem',
          }}
        >
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
            برای استفاده از این اسکیل، ابتدا وارد حساب کاربری خود شوید.
          </p>
          <a href="/login" className="btn btn-primary btn-sm">
            <Icon name="profile" size={14} />
            ورود به حساب
          </a>
        </div>
      )}

      {/* ── Use form ── */}
      {user && (
        <div
          style={{
            background: 'var(--bg-surface)',
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--border)',
            padding: '1.5rem',
            marginBottom: '1.5rem',
          }}
        >
          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '1rem' }}>
            اجرای اسکیل
          </h3>

          {/* Model */}
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
              مدل
            </label>
            <input
              type="text"
              className="input"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="نام مدل"
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

          {/* Run button */}
          <button
            className="btn btn-primary w-full"
            onClick={handleUse}
            disabled={executing}
          >
            {executing ? (
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
                marginTop: '1rem',
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)',
                padding: '1rem',
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
        </div>
      )}

      {/* ── Rating section ── */}
      <div
        style={{
          background: 'var(--bg-surface)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border)',
          padding: '1.25rem',
          marginBottom: '1.5rem',
        }}
      >
        <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.75rem' }}>
          امتیازدهی
        </h3>
        <div className="flex items-center gap-3">
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>امتیاز شما:</span>
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map((r) => (
              <button
                key={r}
                onClick={() => user ? handleRate(r) : toast('ابتدا وارد شوید', 'error')}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: '0.25rem',
                  color: r <= userRating ? 'var(--warning)' : 'var(--text-muted)',
                  opacity: r <= userRating ? 1 : 0.4,
                  transition: 'all 0.15s ease',
                }}
                aria-label={`${r} ستاره`}
              >
                <Icon name="sparkles" size={20} />
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Prompt template preview ── */}
      <div
        style={{
          background: 'var(--bg-surface)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border)',
          padding: '1.25rem',
        }}
      >
        <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.75rem' }}>
          الگوی پرامپت
        </h3>
        <pre
          style={{
            fontSize: '0.8125rem',
            color: 'var(--text-secondary)',
            whiteSpace: 'pre-wrap',
            fontFamily: 'var(--font-mono, monospace)',
            lineHeight: 1.6,
            margin: 0,
            padding: '1rem',
            background: 'var(--bg-elevated)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border)',
          }}
        >
          {skill.prompt_template}
        </pre>
      </div>
    </div>
  )
}
