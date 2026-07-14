'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════════════════════ */

type Assistant = {
  id: number
  name: string
  description: string
  system_prompt: string
  model_id: string | null
  icon: string | null
  is_public: boolean
  user_id: number
  created_at: string
  updated_at: string
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
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <div className="skeleton" style={{ width: '2.5rem', height: '2.5rem', borderRadius: 'var(--radius-md)' }} />
        <div className="skeleton" style={{ width: '8rem', height: '1.25rem' }} />
      </div>
      <div className="skeleton" style={{ width: '100%', height: '0.625rem' }} />
      <div className="skeleton" style={{ width: '75%', height: '0.625rem' }} />
      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
        <div className="skeleton" style={{ width: '4rem', height: '1.25rem', borderRadius: 'var(--radius-full)' }} />
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   Assistant Card
   ═══════════════════════════════════════════════════════════════ */

function AssistantCard({ assistant, onClick }: { assistant: Assistant; onClick: () => void }) {
  return (
    <div
      className="card card-interactive"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.625rem',
        padding: '1.25rem',
        cursor: 'pointer',
      }}
      onClick={onClick}
    >
      {/* Header: icon + name */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
        <div
          style={{
            width: '2.5rem',
            height: '2.5rem',
            borderRadius: 'var(--radius-md)',
            background: 'var(--accent)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <Icon name={(assistant.icon as any) || 'sparkles'} size={20} className="text-white" />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{
            fontSize: '0.9375rem',
            fontWeight: 700,
            color: 'var(--text-primary)',
            lineHeight: 1.4,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {assistant.name}
          </h3>
          {assistant.model_id && (
            <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }} dir="ltr">
              {assistant.model_id}
            </span>
          )}
        </div>
      </div>

      {/* Description */}
      {assistant.description && (
        <p style={{
          fontSize: '0.8125rem',
          color: 'var(--text-secondary)',
          lineHeight: 1.6,
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}>
          {assistant.description}
        </p>
      )}

      {/* Badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.25rem' }}>
        {assistant.is_public ? (
          <span className="badge aurora-cap-green" style={{ fontSize: '0.625rem' }}>
            <Icon name="eye" size={10} />
            عمومی
          </span>
        ) : (
          <span className="badge aurora-cap-default" style={{ fontSize: '0.625rem' }}>
            <Icon name="lock" size={10} />
            خصوصی
          </span>
        )}
        <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginRight: 'auto' }}>
          {new Date(assistant.created_at).toLocaleDateString('fa-IR')}
        </span>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   Assistants List Page
   ═══════════════════════════════════════════════════════════════ */

export default function AssistantsPage() {
  const { token, user, loading: authLoading } = useAuth()
  const router = useRouter()

  const [assistants, setAssistants] = useState<Assistant[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'mine' | 'public'>('all')

  const fetchAssistants = useCallback(async () => {
    if (!token) return
    setLoading(true)
    try {
      const res = await fetch('/api/assistants', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setAssistants(Array.isArray(data) ? data : [])
      } else {
        toast('خطا در دریافت دستیارها', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace('/login')
      return
    }
    fetchAssistants()
  }, [fetchAssistants, authLoading, user, router])

  const filtered = assistants.filter((a) => {
    if (filter === 'mine') return user && a.user_id === user.id
    if (filter === 'public') return a.is_public
    return true
  })

  const filters: { key: typeof filter; label: string }[] = [
    { key: 'all', label: 'همه' },
    { key: 'mine', label: 'دستیارهای من' },
    { key: 'public', label: 'عمومی' },
  ]

  if (authLoading) {
    return (
      <div style={{ maxWidth: '64rem', margin: '0 auto', padding: '1rem 0' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' }}>
          {[1, 2, 3, 4, 5, 6].map((i) => <CardSkeleton key={i} />)}
        </div>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: '64rem', margin: '0 auto', padding: '1rem 0' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.25rem' }}>
            دستیارها
          </h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            دستیارهای هوشمند خود را بسازید و مدیریت کنید
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => router.push('/assistants/new')}
        >
          <Icon name="plus" size={16} />
          دستیار جدید
        </button>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
        {filters.map((f) => (
          <button
            key={f.key}
            className={`btn btn-sm ${filter === f.key ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setFilter(f.key)}
            style={{ fontSize: '0.8125rem' }}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' }}>
          {[1, 2, 3, 4, 5, 6].map((i) => <CardSkeleton key={i} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '3rem 1rem',
            gap: '1rem',
          }}
        >
          <Icon name="sparkles" size={48} className="text-[var(--text-muted)]" style={{ opacity: 0.3 }} />
          <div style={{ textAlign: 'center' }}>
            <h3 style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.375rem' }}>
              دستیاری یافت نشد
            </h3>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              {filter === 'mine'
                ? 'هنوز دستیاری نساخته‌اید. یک دستیار جدید بسازید!'
                : 'دستیاری در این دسته‌بندی وجود ندارد.'}
            </p>
            {filter === 'mine' && (
              <button className="btn btn-primary btn-sm" onClick={() => router.push('/assistants/new')}>
                <Icon name="plus" size={14} />
                ساخت دستیار
              </button>
            )}
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' }}>
          {filtered.map((assistant) => (
            <AssistantCard
              key={assistant.id}
              assistant={assistant}
              onClick={() => router.push(`/assistants/${assistant.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
