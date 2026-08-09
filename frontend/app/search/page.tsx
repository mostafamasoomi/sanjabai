'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'

/* ═══════════════════════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════════════════════ */

type Conversation = {
  id: number
  title: string
  model: string
  messages?: Array<{ role: string; content: string }>
  created_at: string
  updated_at: string
  is_favorite?: boolean
  folder?: string
  tags?: string[]
}

/* ═══════════════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════════════ */

const faDate = (iso: string) =>
  new Date(iso).toLocaleDateString('fa-IR', { year: 'numeric', month: 'long', day: 'numeric' })
const faTime = (iso: string) =>
  new Date(iso).toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' })
const faRelative = (iso: string) => {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'همین الان'
  if (mins < 60) return `${faNum(mins)} دقیقه پیش`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${faNum(hrs)} ساعت پیش`
  const days = Math.floor(hrs / 24)
  if (days < 7) return `${faNum(days)} روز پیش`
  return faDate(iso)
}

function truncate(str: string, len: number) {
  return str.length > len ? str.slice(0, len) + '…' : str
}

/* ═══════════════════════════════════════════════════════════════
   Skeleton
   ═══════════════════════════════════════════════════════════════ */

function CardSkeleton() {
  return (
    <div className="card" style={{ padding: '1.25rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
        <div className="skeleton" style={{ width: '1.5rem', height: '1.5rem', borderRadius: 'var(--radius-sm)' }} />
        <div className="skeleton" style={{ width: '14rem', height: '1rem' }} />
      </div>
      <div className="skeleton" style={{ width: '8rem', height: '0.75rem', marginBottom: '0.5rem' }} />
      <div className="skeleton" style={{ width: '100%', height: '0.625rem', marginBottom: '0.375rem' }} />
      <div className="skeleton" style={{ width: '75%', height: '0.625rem' }} />
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   Conversation Card
   ═══════════════════════════════════════════════════════════════ */

function ConversationCard({ conv, onClick, idx = 0 }: { conv: Conversation; onClick: () => void; idx?: number }) {
  const lastMsg = conv.messages?.length
    ? conv.messages[conv.messages.length - 1]?.content
    : undefined

  return (
    <button
      className="card-interactive slide-up"
      onClick={onClick}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.625rem',
        padding: '1.25rem',
        textAlign: 'right',
        width: '100%',
        cursor: 'pointer',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        background: 'var(--bg-surface)',
        transition: 'all var(--motion-fast) ease',
        animationDelay: `${0.05 + Math.min(idx, 10) * 0.03}s`,
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', minWidth: 0, flex: 1 }}>
          <Icon name="chat" size={18} className="text-[var(--accent)] shrink-0" />
          <span
            style={{
              fontSize: '0.9375rem',
              fontWeight: 600,
              color: 'var(--text-primary)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {conv.title || 'مکالمه بدون عنوان'}
          </span>
        </div>
        {conv.is_favorite && (
          <span className="text-[var(--warning)] shrink-0">★</span>
        )}
        <span className="shrink-0 text-[var(--text-muted)]">
          <Icon name="arrowLeft" size={16} />
        </span>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        {conv.model && (
          <span
            className="badge badge-accent"
            style={{ fontSize: '0.6875rem', padding: '0.125rem 0.5rem' }}
          >
            {conv.model}
          </span>
        )}
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          {faRelative(conv.updated_at || conv.created_at)}
        </span>
      </div>

      {lastMsg && (
        <div
          style={{
            fontSize: '0.8125rem',
            color: 'var(--text-secondary)',
            lineHeight: 1.5,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {truncate(lastMsg, 120)}
        </div>
      )}
    </button>
  )
}

/* ═══════════════════════════════════════════════════════════════
   Search Page
   ═══════════════════════════════════════════════════════════════ */

export default function SearchPage() {
  const { token, user, loading: authLoading } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()
  const inputRef = useRef<HTMLInputElement>(null)

  const [query, setQuery] = useState(searchParams.get('q') || '')
  const [results, setResults] = useState<Conversation[]>([])
  const [recent, setRecent] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)

  // Focus search input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // ── Fetch recent conversations (when no query) ──
  const fetchRecent = useCallback(async () => {
    if (!token) return
    setLoading(true)
    try {
      const res = await fetch('/api/conversations', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        // Backend may return array or paginated {items: [...]} format
        const list: Conversation[] = Array.isArray(data) ? data : (data?.items ?? [])
        setRecent(list.slice(0, 20))
      }
    } catch {
      toast('خطا در دریافت مکالمات', 'error')
    } finally {
      setLoading(false)
    }
  }, [token])

  // ── Search conversations ──
  const searchConversations = useCallback(
    async (q: string) => {
      if (!token || !q.trim()) {
        setResults([])
        fetchRecent()
        return
      }
      setSearching(true)
      try {
        const res = await fetch(`/api/conversations/search?q=${encodeURIComponent(q)}`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (res.ok) {
          const data = await res.json()
          setResults(Array.isArray(data) ? data : [])
        } else {
          toast('خطا در جستجو', 'error')
        }
      } catch {
        toast('خطا در ارتباط با سرور', 'error')
      } finally {
        setSearching(false)
        setLoading(false)
      }
    },
    [token, fetchRecent],
  )

  // ── Debounced search ──
  useEffect(() => {
    if (!query.trim()) {
      setResults([])
      if (token) fetchRecent()
      return
    }

    // Update URL
    const params = new URLSearchParams(window.location.search)
    params.set('q', query)
    const newUrl = `${window.location.pathname}?${params.toString()}`
    window.history.replaceState({}, '', newUrl)

    const timer = setTimeout(() => {
      searchConversations(query)
    }, 300)

    return () => clearTimeout(timer)
  }, [query, token, fetchRecent, searchConversations])

  // ── Initial load ──
  useEffect(() => {
    if (!authLoading && token) {
      if (query.trim()) {
        searchConversations(query)
      } else {
        fetchRecent()
      }
    }
  }, [authLoading, token, query, fetchRecent, searchConversations])

  // ── Not authenticated ──
  if (!authLoading && !user) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', gap: '1.5rem' }}>
        <Icon name="security" size={48} className="text-[var(--text-muted)]" />
        <div className="text-center">
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
            وارد شوید
          </h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            برای جستجوی مکالمات، ابتدا وارد حساب کاربری خود شوید.
          </p>
        </div>
        <button className="btn" onClick={() => router.push('/login')}>
          <Icon name="profile" size={16} />
          ورود به حساب
        </button>
      </div>
    )
  }

  const hasQuery = query.trim().length > 0
  const displayList = hasQuery ? results : recent
  const isLoading = loading || searching

  return (
    <div className="flex flex-col gap-6">
      {/* ── Header ── */}
      <div className="flex items-center gap-3 slide-up">
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
          <Icon name="search" size={20} className="text-[var(--accent)]" />
        </div>
        <div>
          <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
            جستجوی مکالمات
          </h1>
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            {hasQuery
              ? `${faNum(results.length)} نتیجه یافت شد`
              : 'آخرین مکالمات شما'}
          </p>
        </div>
      </div>

      {/* ── Search Input ── */}
      <div
        className="slide-up"
        style={{
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          padding: '0.875rem 1rem',
          background: 'var(--bg-surface)',
          border: '1.5px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          transition: 'border-color var(--motion-fast) ease',
          animationDelay: '0.05s',
        }}
      >
        <Icon
          name="search"
          size={20}
          className={searching ? 'text-[var(--accent)]' : 'text-[var(--text-muted)]'}
        />
        <input
          ref={inputRef}
          type="text"
          placeholder="جستجو در عنوان و محتوای مکالمات…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{
            flex: 1,
            background: 'none',
            border: 'none',
            outline: 'none',
            fontSize: '0.9375rem',
            color: 'var(--text-primary)',
            fontWeight: 500,
          }}
        />
        {query && (
          <button
            onClick={() => {
              setQuery('')
              window.history.replaceState({}, '', window.location.pathname)
              inputRef.current?.focus()
            }}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--text-muted)',
              padding: '0.25rem',
              display: 'flex',
              alignItems: 'center',
            }}
            aria-label="پاک کردن جستجو"
          >
            <Icon name="close" size={18} />
          </button>
        )}
      </div>

      {/* ── Loading skeletons ── */}
      {isLoading && (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      )}

      {/* ── Results ── */}
      {!isLoading && (
        <div className="flex flex-col gap-3">
          {displayList.length > 0 ? (
            displayList.map((conv, idx) => (
              <ConversationCard
                key={conv.id}
                conv={conv}
                idx={idx}
                onClick={() => router.push(`/chat?conversation=${conv.id}`)}
              />
            ))
          ) : (
            /* ── Empty state ── */
            <div
              className="slide-up"
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '4rem 2rem',
                gap: '1rem',
                animationDelay: '0.1s',
              }}
            >
              <Icon
                name={hasQuery ? 'search' : 'chat'}
                size={48}
                className="text-[var(--text-muted)]"
                style={{ opacity: 0.4 }}
              />
              <div className="text-center">
                <h3
                  style={{
                    fontSize: '1rem',
                    fontWeight: 600,
                    color: 'var(--text-secondary)',
                    marginBottom: '0.375rem',
                  }}
                >
                  {hasQuery ? 'نتیجه‌ای یافت نشد' : 'هنوز مکالمه‌ای ندارید'}
                </h3>
                <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                  {hasQuery
                    ? 'عبارت جستجو را تغییر دهید یا فیلترها را بررسی کنید.'
                    : 'با شروع یک مکالمه جدید، مکالمات شما اینجا نمایش داده می‌شوند.'}
                </p>
              </div>
              {!hasQuery && (
                <button className="btn btn-primary" onClick={() => router.push('/chat')}>
                  <Icon name="chat" size={16} />
                  شروع مکالمه
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
