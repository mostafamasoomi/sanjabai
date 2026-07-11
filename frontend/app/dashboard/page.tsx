'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon, type IconName } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════════════════════ */

type UserProfile = {
  id: number
  email: string
  username?: string
  phone?: string
  plan: string
  is_active: boolean
  created_at: string
}

type Usage = {
  total_spend: number
  turns: number
  total_tokens: number
}

type LedgerEntry = {
  id: number
  amount: number
  balance_after: number
  reason: string
  created_at: string
}

type ModelItem = { id: string }

/* ═══════════════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════════════ */

const faNum = (n: number) => n.toLocaleString('fa-IR')
const faDate = (iso: string) => new Date(iso).toLocaleDateString('fa-IR', { year: 'numeric', month: 'long', day: 'numeric' })
const faTime = (iso: string) => new Date(iso).toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' })

const planLabels: Record<string, string> = {
  free: 'رایگان',
  pro: 'حرفه‌ای',
  enterprise: 'سازمانی',
}

const planBadgeClass: Record<string, string> = {
  free: 'badge',
  pro: 'badge badge-accent',
  enterprise: 'badge badge-positive',
}

/* ═══════════════════════════════════════════════════════════════
   Skeleton helpers
   ═══════════════════════════════════════════════════════════════ */

function StatCardSkeleton() {
  return (
    <div className="card">
      <div className="skeleton" style={{ width: '6rem', height: '0.75rem', marginBottom: '0.75rem' }} />
      <div className="skeleton" style={{ width: '8rem', height: '1.75rem', marginBottom: '0.5rem' }} />
      <div className="skeleton" style={{ width: '4rem', height: '0.625rem' }} />
    </div>
  )
}

function LedgerSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div className="skeleton" style={{ width: '2rem', height: '2rem', borderRadius: 'var(--radius-sm)' }} />
            <div>
              <div className="skeleton" style={{ width: '6rem', height: '0.75rem', marginBottom: '0.375rem' }} />
              <div className="skeleton" style={{ width: '4rem', height: '0.625rem' }} />
            </div>
          </div>
          <div className="skeleton" style={{ width: '5rem', height: '0.875rem' }} />
        </div>
      ))}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   Stat Card
   ═══════════════════════════════════════════════════════════════ */

function StatCard({
  icon,
  label,
  value,
  sub,
  accentColor,
}: {
  icon: IconName
  label: string
  value: string
  sub?: string
  accentColor?: string
}) {
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: 500 }}>{label}</span>
        <div
          style={{
            width: '2rem',
            height: '2rem',
            borderRadius: 'var(--radius-sm)',
            background: accentColor ? `${accentColor}15` : 'var(--accent-dim)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Icon name={icon} size={16} className="text-[var(--accent)]" />
        </div>
      </div>
      <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>{sub}</div>
      )}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   Quick Action Button
   ═══════════════════════════════════════════════════════════════ */

function QuickAction({
  icon,
  label,
  description,
  onClick,
}: {
  icon: IconName
  label: string
  description: string
  onClick: () => void
}) {
  return (
    <button
      className="card-interactive"
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        padding: '1rem',
        textAlign: 'right',
        width: '100%',
        cursor: 'pointer',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        background: 'var(--bg-surface)',
        transition: 'all var(--motion-fast) ease',
      }}
    >
      <div
        style={{
          width: '2.5rem',
          height: '2.5rem',
          borderRadius: 'var(--radius-sm)',
          background: 'var(--accent-dim)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <Icon name={icon} size={18} className="text-[var(--accent)]" />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>{label}</div>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.125rem' }}>{description}</div>
      </div>
      <span className="shrink-0 text-[var(--text-muted)]">
        <Icon name="arrowLeft" size={16} />
      </span>
    </button>
  )
}

/* ═══════════════════════════════════════════════════════════════
   Ledger Entry Row
   ═══════════════════════════════════════════════════════════════ */

function LedgerRow({ entry }: { entry: LedgerEntry }) {
  const isCredit = entry.amount > 0
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.75rem 0',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', minWidth: 0 }}>
        <div
          style={{
            width: '2rem',
            height: '2rem',
            borderRadius: 'var(--radius-sm)',
            background: isCredit ? 'color-mix(in srgb, var(--positive) 12%, transparent)' : 'color-mix(in srgb, var(--danger) 12%, transparent)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <Icon
            name={isCredit ? 'wallet' : 'payment'}
            size={14}
            className={isCredit ? 'text-[var(--positive)]' : 'text-[var(--danger)]'}
          />
        </div>
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontSize: '0.8125rem',
              fontWeight: 500,
              color: 'var(--text-primary)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {entry.reason}
          </div>
          <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: '0.125rem' }}>
            {faDate(entry.created_at)} — {faTime(entry.created_at)}
          </div>
        </div>
      </div>
      <div style={{ textAlign: 'left', flexShrink: 0, marginLeft: '1rem' }}>
        <div
          style={{
            fontSize: '0.875rem',
            fontWeight: 600,
            color: isCredit ? 'var(--positive)' : 'var(--danger)',
          }}
        >
          {isCredit ? '+' : ''}{faNum(entry.amount)} <span style={{ fontSize: '0.625rem', fontWeight: 400 }}>تومان</span>
        </div>
        <div style={{ fontSize: '0.625rem', color: 'var(--text-muted)', textAlign: 'left' }}>
          موجودی: {faNum(entry.balance_after)}
        </div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   Info Row (for account card)
   ═══════════════════════════════════════════════════════════════ */

function InfoRow({ icon, label, value }: { icon: IconName; label: string; value: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
        <span className="shrink-0 text-[var(--text-muted)]">
          <Icon name={icon} size={14} />
        </span>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{label}</span>
      </div>
      <span
        style={{
          fontSize: '0.8125rem',
          fontWeight: 500,
          color: 'var(--text-primary)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          textAlign: 'left',
        }}
      >
        {value}
      </span>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   Main Dashboard Page
   ═══════════════════════════════════════════════════════════════ */

export default function DashboardPage() {
  const { token, user, loading: authLoading } = useAuth()
  const router = useRouter()

  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [usage, setUsage] = useState<Usage | null>(null)
  const [balance, setBalance] = useState<number | null>(null)
  const [ledger, setLedger] = useState<LedgerEntry[]>([])
  const [models, setModels] = useState<ModelItem[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchData = useCallback(async (isRefresh = false) => {
    if (!token) { setLoading(false); return }

    if (isRefresh) setRefreshing(true)
    else setLoading(true)

    const headers = { Authorization: `Bearer ${token}` }

    try {
      const [meRes, usageRes, walletRes, ledgerRes, modelsRes] = await Promise.allSettled([
        fetch('/api/me', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        fetch('/me/usage', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        fetch('/api/wallet', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        fetch('/api/wallet/ledger', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        fetch('/v1/models', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
      ])

      if (meRes.status === 'fulfilled') setProfile(meRes.value)
      if (usageRes.status === 'fulfilled') setUsage(usageRes.value)
      if (walletRes.status === 'fulfilled') setBalance(walletRes.value?.balance ?? 0)
      if (ledgerRes.status === 'fulfilled') setLedger(Array.isArray(ledgerRes.value) ? ledgerRes.value.slice(0, 10) : [])
      if (modelsRes.status === 'fulfilled') setModels(modelsRes.value?.data ?? [])

      const failed = [meRes, usageRes, walletRes, ledgerRes, modelsRes].filter((r) => r.status === 'rejected')
      if (failed.length === 5) {
        toast('خطا در دریافت اطلاعات داشبورد', 'error')
      } else if (failed.length > 0) {
        toast('برخی اطلاعات بارگذاری نشد', 'info')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [token])

  useEffect(() => {
    if (!authLoading) fetchData()
  }, [authLoading, fetchData])

  /* ─── Not authenticated ─── */
  if (!authLoading && !user) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', gap: '1.5rem' }}>
        <Icon name="security" size={48} className="text-[var(--text-muted)]" />
        <div style={{ textAlign: 'center' }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>وارد شوید</h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>برای مشاهده داشبورد، ابتدا وارد حساب کاربری خود شوید.</p>
        </div>
        <button className="btn" onClick={() => router.push('/login')}>
          <Icon name="profile" size={16} />
          ورود به حساب
        </button>
      </div>
    )
  }

  /* ─── Loading state ─── */
  if (authLoading || loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        {/* Header skeleton */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div className="skeleton" style={{ width: '12rem', height: '1.75rem', marginBottom: '0.5rem' }} />
            <div className="skeleton" style={{ width: '8rem', height: '0.875rem' }} />
          </div>
          <div className="skeleton" style={{ width: '5rem', height: '1.75rem', borderRadius: 'var(--radius-lg)' }} />
        </div>

        {/* Stat cards skeleton */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
          <StatCardSkeleton />
          <StatCardSkeleton />
          <StatCardSkeleton />
          <StatCardSkeleton />
        </div>

        {/* Content skeleton */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '1.5rem' }}>
          <div className="card">
            <div className="skeleton" style={{ width: '8rem', height: '1rem', marginBottom: '1rem' }} />
            <LedgerSkeleton />
          </div>
          <div className="card">
            <div className="skeleton" style={{ width: '6rem', height: '1rem', marginBottom: '1rem' }} />
            <div className="skeleton" style={{ width: '100%', height: '6rem' }} />
          </div>
        </div>
      </div>
    )
  }

  const displayName = profile?.username || profile?.email?.split('@')[0] || 'کاربر'
  const plan = profile?.plan || 'free'
  const recentLedger = ledger.slice(0, 10)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* ─── Header ─── */}
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
            سلام، {displayName}
          </h1>
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            خوش آمدید به داشبورد مولتی‌ای
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span className={planBadgeClass[plan] || 'badge'}>
            {planLabels[plan] || plan}
          </span>
          <button
            className="btn btn-sm"
            onClick={() => fetchData(true)}
            disabled={refreshing}
            title="بروزرسانی"
            style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}
          >
            <span className={refreshing ? 'animate-spin' : ''}>
              <Icon name="refresh" size={14} />
            </span>
            بروزرسانی
          </button>
        </div>
      </header>

      {/* ─── Stat Cards Grid ─── */}
      <section
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '1rem',
        }}
      >
        <StatCard
          icon="wallet"
          label="موجودی کیف پول"
          value={`${faNum(balance ?? 0)}`}
          sub="تومان"
        />
        <StatCard
          icon="payment"
          label="کل هزینه"
          value={`${faNum(usage?.total_spend ?? 0)}`}
          sub="تومان"
        />
        <StatCard
          icon="chat"
          label="تعداد مکالمات"
          value={faNum(usage?.turns ?? 0)}
          sub="مکالمه"
        />
        <StatCard
          icon="code"
          label="کل توکن‌ها"
          value={faNum(usage?.total_tokens ?? 0)}
          sub="توکن"
        />
      </section>

      {/* ─── Main Content Grid ─── */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '1.5rem',
          alignItems: 'start',
        }}
      >
        {/* Recent Activity / Ledger */}
        <div className="card" style={{ overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span className="text-[var(--accent)]">
                <Icon name="history" size={18} />
              </span>
              <h2 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>فعالیت اخیر</h2>
            </div>
            <button
              className="btn btn-sm"
              onClick={() => router.push('/wallet')}
              style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.75rem' }}
            >
              مشاهده همه
              <Icon name="arrowLeft" size={12} />
            </button>
          </div>

          {recentLedger.length === 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '2.5rem 1rem', gap: '0.75rem' }}>
              <span className="text-[var(--text-muted)] opacity-50">
                <Icon name="history" size={32} />
              </span>
              <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', textAlign: 'center' }}>
                هنوز تراکنشی ثبت نشده است
              </p>
              <button className="btn btn-sm" onClick={() => router.push('/wallet')}>
                <Icon name="wallet" size={14} />
                شارژ کیف پول
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {recentLedger.map((entry) => (
                <LedgerRow key={entry.id} entry={entry} />
              ))}
            </div>
          )}
        </div>

        {/* Right column: Quick Actions + Account */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Quick Actions */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
              <span className="text-[var(--accent)]">
                <Icon name="dashboard" size={18} />
              </span>
              <h2 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>دسترسی سریع</h2>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <QuickAction
                icon="chat"
                label="شروع مکالمه"
                description="گفتگو با هوش مصنوعی"
                onClick={() => router.push('/chat')}
              />
              <QuickAction
                icon="wallet"
                label="کیف پول"
                description="شارژ و مدیریت حساب"
                onClick={() => router.push('/wallet')}
              />
              <QuickAction
                icon="models"
                label="مدل‌ها"
                description={`${faNum(models.length)} مدل در دسترس`}
                onClick={() => router.push('/models')}
              />
            </div>
          </div>

          {/* Account Info */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
              <span className="text-[var(--accent)]">
                <Icon name="profile" size={18} />
              </span>
              <h2 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>اطلاعات حساب</h2>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <InfoRow icon="profile" label="ایمیل" value={profile?.email || '—'} />
              {profile?.username && <InfoRow icon="profile" label="نام کاربری" value={profile.username} />}
              {profile?.phone && <InfoRow icon="notification" label="تلفن" value={profile.phone} />}
              <InfoRow icon="security" label="وضعیت" value={profile?.is_active ? 'فعال' : 'غیرفعال'} />
              <InfoRow
                icon="dashboard"
                label="تاریخ عضویت"
                value={profile?.created_at ? faDate(profile.created_at) : '—'}
              />
            </div>
            <div className="divider" style={{ margin: '1rem 0' }} />
            <button
              className="btn btn-sm"
              onClick={() => router.push('/profile')}
              style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.375rem' }}
            >
              <Icon name="settings" size={14} />
              مدیریت حساب
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
