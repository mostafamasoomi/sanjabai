'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon, type IconName } from '@/components/ui/Icon'
import { Num, faNum, faPercent, faDate, faTime } from '@/lib/format'

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
  total_spent_this_month: number
  turns: number
  total_input_tokens_this_month: number
}

type LedgerEntry = {
  id: number
  amount: number
  balance_after: number
  reason: string
  created_at: string
}

type ModelItem = { id: string }

type Subscription = {
  id: number
  user_id: number
  plan: string
  starts_at: string
  ends_at: string
  status: string
  monthly_token_quota: number
  tokens_used_this_period: number
  auto_renew: boolean
  price_paid: number
} | null

type SubscriptionPlan = {
  id: number
  name_fa: string
  name_en: string
  price_monthly: number
  monthly_token_quota: number
  daily_token_limit: number
  features: string[]
} | null

type BillingSettings = {
  user_id: number
  payg_enabled: boolean
  payg_hard_limit: number | null
  notify_on_usage_pct: number
} | null

/* ═══════════════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════════════ */

/* Numerals, dates and money all come from lib/format — see the note there on
   why this page no longer calls toLocaleString directly. */

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
    <div className="flex flex-col gap-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex justify-between items-center">
          <div className="flex items-center gap-3">
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
  unit,
  lead = false,
}: {
  icon: IconName
  label: string
  value: number
  unit?: string
  /** The one card on the page allowed the top step of the type scale. */
  lead?: boolean
}) {
  return (
    <div className={`card stat-card${lead ? ' stat-card--lead' : ''}`}>
      <div className="stat-card__head">
        <span className="stat-card__label">{label}</span>
        <div className="stat-card__icon">
          <Icon name={icon} size={16} />
        </div>
      </div>
      <Num className="stat-card__value" value={value} />
      {unit && <div className="stat-card__unit">{unit}</div>}
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
      <div className="flex-1 min-w-0">
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

function LedgerRow({ entry, idx = 0 }: { entry: LedgerEntry; idx?: number }) {
  const isCredit = entry.amount > 0
  return (
    <div
      className="flex items-center justify-between py-3 border-b border-[var(--border)] slide-up"
      style={{ animationDelay: `${0.2 + Math.min(idx, 10) * 0.03}s` }}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div
          className="w-8 h-8 rounded-[var(--radius-sm)] flex items-center justify-center shrink-0"
          style={{
            background: isCredit ? 'color-mix(in srgb, var(--positive) 12%, transparent)' : 'color-mix(in srgb, var(--danger) 12%, transparent)',
          }}
        >
          <Icon
            name={isCredit ? 'wallet' : 'payment'}
            size={14}
            className={isCredit ? 'text-[var(--positive)]' : 'text-[var(--danger)]'}
          />
        </div>
        <div className="min-w-0">
          <div className="text-[13px] font-medium text-[var(--text-primary)] overflow-hidden text-ellipsis whitespace-nowrap">
            {entry.reason}
          </div>
          <div className="text-[11px] text-[var(--text-muted)] mt-0.5">
            {faDate(entry.created_at)} — {faTime(entry.created_at)}
          </div>
        </div>
      </div>
      <div className="text-end shrink-0 ms-4">
        <div
          className="text-sm font-semibold"
          style={{ color: isCredit ? 'var(--positive)' : 'var(--danger)' }}
        >
          <Num value={entry.amount} unit="تومان" signed />
        </div>
        <div className="text-[10px] text-[var(--text-muted)] text-end">
          موجودی: <Num value={entry.balance_after} />
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
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 min-w-0">
        <span className="shrink-0 text-[var(--text-muted)]">
          <Icon name={icon} size={14} />
        </span>
        <span className="text-xs text-[var(--text-secondary)]">{label}</span>
      </div>
      <span className="text-[13px] font-medium text-[var(--text-primary)] overflow-hidden text-ellipsis whitespace-nowrap text-end">
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

  // Subscription & Billing state
  const [subscription, setSubscription] = useState<Subscription>(null)
  const [subscriptionPlan, setSubscriptionPlan] = useState<SubscriptionPlan>(null)
  const [billingSettings, setBillingSettings] = useState<BillingSettings>(null)
  const [paygLoading, setPaygLoading] = useState(false)
  const [showHardLimitInput, setShowHardLimitInput] = useState(false)
  const [hardLimitValue, setHardLimitValue] = useState('')
  const [hardLimitLoading, setHardLimitLoading] = useState(false)

  const fetchData = useCallback(async (isRefresh = false) => {
    if (!token) { setLoading(false); return }

    if (isRefresh) setRefreshing(true)
    else setLoading(true)

    const headers = { Authorization: `Bearer ${token}` }

    try {
      const [meRes, usageRes, walletRes, ledgerRes, modelsRes, subRes, billingRes] = await Promise.allSettled([
        fetch('/api/auth/me', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        fetch('/api/me/usage', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        fetch('/api/wallet', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        fetch('/api/wallet/ledger', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        fetch('/api/models', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        fetch('/api/subscription', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        fetch('/api/billing/settings', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
      ])

      if (meRes.status === 'fulfilled') setProfile(meRes.value)
      if (usageRes.status === 'fulfilled') setUsage(usageRes.value)
      if (walletRes.status === 'fulfilled') setBalance(walletRes.value?.balance ?? 0)
      if (ledgerRes.status === 'fulfilled') setLedger(Array.isArray(ledgerRes.value) ? ledgerRes.value.slice(0, 10) : [])
      if (modelsRes.status === 'fulfilled') setModels(modelsRes.value?.data ?? [])
      if (subRes.status === 'fulfilled') {
        setSubscription(subRes.value?.subscription ?? null)
        setSubscriptionPlan(subRes.value?.plan ?? null)
      }
      if (billingRes.status === 'fulfilled') setBillingSettings(billingRes.value ?? null)

      const failed = [meRes, usageRes, walletRes, ledgerRes, modelsRes, subRes, billingRes].filter((r) => r.status === 'rejected')
      if (failed.length === 7) {
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

  /* ─── Toggle PAYG ─── */
  const togglePayg = useCallback(async () => {
    if (!token || !billingSettings) return
    setPaygLoading(true)
    try {
      const res = await fetch('/api/billing/settings', {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ payg_enabled: !billingSettings.payg_enabled }),
      })
      if (res.ok) {
        setBillingSettings((prev) => prev ? { ...prev, payg_enabled: !prev.payg_enabled } : prev)
        toast(billingSettings.payg_enabled ? 'پرداخت به ازای مصرف غیرفعال شد' : 'پرداخت به ازای مصرف فعال شد', 'success')
      } else {
        toast('خطا در تغییر تنظیمات', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setPaygLoading(false)
    }
  }, [token, billingSettings])

  /* ─── Set Hard Limit ─── */
  const setHardLimit = useCallback(async () => {
    if (!token) return
    const parsed = parseInt(hardLimitValue, 10)
    if (isNaN(parsed) || parsed < 0) {
      toast('لطفاً مبلغ معتبری وارد کنید', 'error')
      return
    }
    setHardLimitLoading(true)
    try {
      const res = await fetch('/api/billing/settings', {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ payg_hard_limit: parsed }),
      })
      if (res.ok) {
        setBillingSettings((prev) => prev ? { ...prev, payg_hard_limit: parsed } : prev)
        setShowHardLimitInput(false)
        setHardLimitValue('')
        toast('سقف هزینه با موفقیت تنظیم شد', 'success')
      } else {
        toast('خطا در تنظیم سقف هزینه', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setHardLimitLoading(false)
    }
  }, [token, hardLimitValue])

  /* ─── Not authenticated ─── */
  if (!authLoading && !user) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', gap: '1.5rem' }}>
        <Icon name="security" size={48} className="text-[var(--text-muted)]" />
        <div className="text-center">
          {/* h1: this branch replaces the whole page, so it owns the outline. */}
          <h1 className="page-title" style={{ marginBottom: '0.5rem' }}>وارد شوید</h1>
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
      <div className="flex flex-col gap-6">
        {/* Header skeleton */}
        <div className="flex justify-between items-center">
          <div>
            <div className="skeleton" style={{ width: '12rem', height: '1.75rem', marginBottom: '0.5rem' }} />
            <div className="skeleton" style={{ width: '8rem', height: '0.875rem' }} />
          </div>
          <div className="skeleton" style={{ width: '5rem', height: '1.75rem', borderRadius: 'var(--radius-lg)' }} />
        </div>

        {/* Stat cards skeleton */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-4)' }}>
          <StatCardSkeleton />
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

  // Deliberately no email-local-part fallback: it produced greetings like
  // "سلام، user" — a Latin fragment of an address presented as a person's
  // name. A generic Persian noun is less wrong than a wrong name.
  const displayName = profile?.username || 'کاربر'
  const plan = profile?.plan || 'free'
  const recentLedger = ledger.slice(0, 10)

  // Subscription derived values
  const subStatus = subscription?.status || 'none'
  const subStatusColor = subStatus === 'active' ? 'var(--positive)' : subStatus === 'cancelled' ? 'var(--danger)' : 'var(--text-muted)'
  const subStatusLabel = subStatus === 'active' ? 'فعال' : subStatus === 'cancelled' ? 'لغو شده' : 'بدون اشتراک'
  const tokenQuota = subscription?.monthly_token_quota ?? 0
  const tokensUsed = subscription?.tokens_used_this_period ?? 0
  const tokenPct = tokenQuota > 0 ? Math.min((tokensUsed / tokenQuota) * 100, 100) : 0
  const planName = subscriptionPlan?.name_fa || planLabels[plan] || plan

  return (
    // One 12-column grid for the whole page. Each card declares how much of
    // the measure it takes, so every row fills the width instead of collapsing
    // to a half-width column pinned to the inline-start edge.
    <div className="dash-grid">
      {/* ─── Header ─── */}
      <header className="dash-span-12 slide-up" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 className="page-title">
            سلام، {displayName}
          </h1>
          <p className="page-subtitle">
            خوش آمدید به داشبورد مولتیای
          </p>
        </div>
        <div className="flex items-center gap-3">
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

      {/* ─── Stat row: four equal columns across the full measure ─── */}
      <div className="dash-span-3 slide-up" style={{ animationDelay: '0.05s' }}>
        <StatCard icon="wallet" label="موجودی کیف پول" value={balance ?? 0} unit="تومان" lead />
      </div>
      <div className="dash-span-3 slide-up" style={{ animationDelay: '0.1s' }}>
        <StatCard icon="payment" label="کل هزینه" value={usage?.total_spent_this_month ?? 0} unit="تومان" />
      </div>
      <div className="dash-span-3 slide-up" style={{ animationDelay: '0.15s' }}>
        <StatCard icon="chat" label="تعداد مکالمات" value={(usage as any)?.event_count_this_month ?? 0} unit="مکالمه" />
      </div>
      <div className="dash-span-3 slide-up" style={{ animationDelay: '0.2s' }}>
        <StatCard icon="code" label="کل توکن‌ها" value={usage?.total_input_tokens_this_month ?? 0} unit="توکن" />
      </div>

      {/* ─── Subscription + activity row ─── */}
        <div className="card dash-span-4 flex flex-col gap-3 slide-up" style={{ animationDelay: '0.25s' }}>
          <div className="flex items-center justify-between">
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: 500 }}>وضعیت اشتراک</span>
            <div
              style={{
                width: '2rem',
                height: '2rem',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--accent-dim)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Icon name="dashboard" size={16} className="text-[var(--accent)]" />
            </div>
          </div>

          {/* Plan name */}
          <div style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            {planName}
          </div>

          {/* Status badge */}
          <div className="flex items-center gap-2">
            <span
              style={{
                display: 'inline-block',
                width: '0.5rem',
                height: '0.5rem',
                borderRadius: '50%',
                background: subStatusColor,
              }}
            />
            <span style={{ fontSize: '0.75rem', fontWeight: 500, color: subStatusColor }}>
              {subStatusLabel}
            </span>
          </div>

          {/* Token usage progress bar */}
          {tokenQuota > 0 && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                  توکن مصرف شده
                </span>
                <span className="num" style={{ fontSize: 'var(--fs-2xs)', color: 'var(--text-secondary)' }}>
                  {faNum(tokensUsed)} / {faNum(tokenQuota)}
                </span>
              </div>
              <div
                style={{
                  width: '100%',
                  height: '6px',
                  borderRadius: '3px',
                  background: 'var(--border)',
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${tokenPct}%`,
                    height: '100%',
                    borderRadius: '3px',
                    background: tokenPct > 90 ? 'var(--danger)' : tokenPct > 70 ? 'var(--warning)' : 'var(--accent)',
                    transition: 'width 0.5s ease',
                  }}
                />
              </div>
            </div>
          )}

          {/* Ends at */}
          {subscription?.ends_at && (
            <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
              تاریخ پایان: {faDate(subscription.ends_at)}
            </div>
          )}

          {/* Change plan button */}
          <button
            className="btn btn-sm"
            onClick={() => router.push('/pricing')}
            style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.375rem', marginTop: '0.25rem' }}
          >
            <Icon name="payment" size={14} />
            تغییر پلن
          </button>
        </div>

        {/* Recent Activity / Ledger — the widest card on the page, because it
            is a list of long rows and the only one that benefits from run. */}
        <div className="card dash-span-8 overflow-hidden slide-up" style={{ animationDelay: '0.3s' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
            <div className="flex items-center gap-2">
              <span className="text-[var(--accent)]">
                <Icon name="history" size={18} />
              </span>
              <h2 className="card-title">فعالیت اخیر</h2>
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
            <div className="empty-state">
              <span className="empty-state__icon">
                <Icon name="history" size={22} />
              </span>
              <p className="empty-state__title">هنوز تراکنشی ثبت نشده است</p>
              <p className="empty-state__desc">
                پس از اولین شارژ یا مصرف، تراکنش‌ها اینجا فهرست می‌شوند.
              </p>
              <button className="btn btn-sm btn-secondary" onClick={() => router.push('/wallet')}>
                <Icon name="wallet" size={14} />
                شارژ کیف پول
              </button>
            </div>
          ) : (
            <div className="flex flex-col">
              {recentLedger.map((entry, idx) => (
                <LedgerRow key={entry.id} entry={entry} idx={idx} />
              ))}
            </div>
          )}
        </div>

        {/* ─── Bottom row: three equal thirds ─── */}
          {/* Quick Actions */}
          <div className="card dash-span-4 slide-up" style={{ animationDelay: '0.35s' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
              <span className="text-[var(--accent)]">
                <Icon name="dashboard" size={18} />
              </span>
              <h2 className="card-title">دسترسی سریع</h2>
            </div>
            <div className="flex flex-col gap-3">
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
              <QuickAction
                icon="payment"
                label="خرید بسته اعتباری"
                description="خرید بسته اعتباری ویژه"
                onClick={() => router.push('/pricing#credit-packages')}
              />
              <QuickAction
                icon="settings"
                label="تنظیمات صورتحساب"
                description="مدیریت پرداخت به ازای مصرف"
                onClick={() => {
                  const el = document.getElementById('payg-section')
                  if (el) el.scrollIntoView({ behavior: 'smooth' })
                }}
              />
            </div>
          </div>

          {/* Account Info */}
          <div className="card dash-span-4 slide-up" style={{ animationDelay: '0.4s' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
              <span className="text-[var(--accent)]">
                <Icon name="profile" size={18} />
              </span>
              <h2 className="card-title">اطلاعات حساب</h2>
            </div>
            <div className="flex flex-col gap-3">
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

          {/* ─── PAYG Toggle Section ─── */}
          <div className="card dash-span-4 slide-up" id="payg-section" style={{ animationDelay: '0.45s' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
              <span className="text-[var(--accent)]">
                <Icon name="payment" size={18} />
              </span>
              <h2 className="card-title">پرداخت به ازای مصرف</h2>
            </div>

            {/* Toggle row */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.75rem 0',
              }}
            >
              <div>
                <div style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--text-primary)' }}>
                  پرداخت به ازای مصرف (PAYG)
                </div>
                <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                  {billingSettings?.payg_enabled ? 'فعال' : 'غیرفعال'}
                </div>
              </div>
              <button
                onClick={togglePayg}
                disabled={paygLoading || !billingSettings}
                style={{
                  width: '3rem',
                  height: '1.625rem',
                  borderRadius: '0.8125rem',
                  border: 'none',
                  cursor: paygLoading ? 'not-allowed' : 'pointer',
                  background: billingSettings?.payg_enabled ? 'var(--accent)' : 'var(--border)',
                  position: 'relative',
                  transition: 'background 0.2s ease',
                  opacity: paygLoading ? 0.6 : 1,
                  flexShrink: 0,
                }}
              >
                <div
                  style={{
                    width: '1.25rem',
                    height: '1.25rem',
                    borderRadius: '50%',
                    background: 'var(--text-on-accent)',
                    position: 'absolute',
                    top: '0.1875rem',
                    right: billingSettings?.payg_enabled ? '0.1875rem' : 'auto',
                    left: billingSettings?.payg_enabled ? 'auto' : '0.1875rem',
                    transition: 'all 0.2s ease',
                    boxShadow: 'var(--shadow-sm)',
                  }}
                />
              </button>
            </div>

            {/* Hard limit display */}
            <div style={{ padding: '0.5rem 0', borderTop: '1px solid var(--border)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>سقف هزینه</span>
                <span className="num" style={{ fontSize: 'var(--fs-sm)', fontWeight: 500, color: 'var(--text-primary)' }}>
                  {billingSettings?.payg_hard_limit != null
                    ? `${faNum(billingSettings.payg_hard_limit)} تومان`
                    : 'تعیین نشده'
                  }
                </span>
              </div>
              {showHardLimitInput ? (
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                  <input
                    type="number"
                    value={hardLimitValue}
                    onChange={(e) => setHardLimitValue(e.target.value)}
                    placeholder="مبلغ (تومان)"
                    style={{
                      flex: 1,
                      padding: '0.5rem 0.75rem',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--border)',
                      background: 'var(--bg)',
                      color: 'var(--text-primary)',
                      fontSize: '0.8125rem',
                      fontFeatureSettings: '"tnum"',
                      outline: 'none',
                    }}
                  />
                  <button
                    className="btn btn-sm shrink-0"
                    onClick={setHardLimit}
                    disabled={hardLimitLoading}
                  >
                    {hardLimitLoading ? '...' : 'ذخیره'}
                  </button>
                  <button
                    className="btn btn-sm"
                    onClick={() => { setShowHardLimitInput(false); setHardLimitValue('') }}
                    style={{ flexShrink: 0, background: 'transparent', border: '1px solid var(--border)' }}
                  >
                    لغو
                  </button>
                </div>
              ) : (
                <button
                  className="btn btn-sm"
                  onClick={() => setShowHardLimitInput(true)}
                  style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.375rem', marginTop: '0.25rem' }}
                >
                  <Icon name="settings" size={14} />
                  تنظیم سقف هزینه
                </button>
              )}
            </div>

            {/* Notify percentage */}
            {billingSettings?.notify_on_usage_pct != null && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.5rem 0', borderTop: '1px solid var(--border)' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>اعلام درصد مصرف</span>
                <span className="num" style={{ fontSize: 'var(--fs-sm)', fontWeight: 500, color: 'var(--text-primary)' }}>
                  {faPercent(billingSettings.notify_on_usage_pct)}
                </span>
              </div>
            )}

            {/* Info text */}
            <div
              style={{
                marginTop: '0.75rem',
                padding: '0.625rem 0.75rem',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--accent-dim)',
                fontSize: '0.6875rem',
                color: 'var(--text-secondary)',
                lineHeight: 1.6,
              }}
            >
              با فعال بودن پرداخت به ازای مصرف، از موجودی کیف پول شما کسر می‌شود
            </div>
          </div>
    </div>
  )
}
