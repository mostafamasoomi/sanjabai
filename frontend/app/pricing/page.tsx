'use client'

import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════════════════════════════════ */

type Plan = {
  id: string
  name_fa: string
  name_en: string
  price_monthly: number
  monthly_token_quota: number
  daily_token_limit: number
  models_allowed: string[] | null
  priority_queue: boolean
  features: string[]
}

type CreditPackage = {
  id: string
  name_fa: string
  name_en: string
  base_amount: number
  bonus_percent: number
  total_credits: number
}

type Subscription = {
  plan: string
  status: string
  expires_at?: string
  started_at?: string
}

/* ═══════════════════════════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════════════════════════ */

const fmtToman = (n: number) => `${n.toLocaleString('fa-IR')} تومان`
const fmtIRR = (n: number) => n.toLocaleString('fa-IR')

function formatTokens(quota: number): string {
  if (quota === 0) return 'نامحدود'
  if (quota >= 1_000_000) return `${(quota / 1_000_000).toLocaleString('fa-IR')} میلیون توکن/ماه`
  if (quota >= 1_000) return `${(quota / 1_000).toLocaleString('fa-IR')} هزار توکن/ماه`
  return `${quota.toLocaleString('fa-IR')} توکن/ماه`
}

const planColors: Record<string, { bg: string; border: string; accent: string }> = {
  free: { bg: 'var(--bg-surface)', border: 'var(--border)', accent: 'var(--text-muted)' },
  basic: { bg: 'var(--bg-surface)', border: 'var(--border)', accent: 'var(--accent)' },
  pro: { bg: 'var(--bg-surface)', border: 'var(--accent)', accent: 'var(--accent)' },
  unlimited: {
    bg: 'linear-gradient(135deg, rgba(124,111,247,0.08) 0%, rgba(103,232,249,0.06) 50%, rgba(167,139,250,0.08) 100%)',
    border: 'var(--accent)',
    accent: 'var(--accent)',
  },
}

/* ═══════════════════════════════════════════════════════════════════════════
   Skeleton Components
   ═══════════════════════════════════════════════════════════════════════════ */

function PlanCardSkeleton() {
  return (
    <div className="card" style={{ padding: 28, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="skeleton" style={{ width: 60, height: 20, borderRadius: 'var(--radius-sm)' }} />
      <div className="skeleton" style={{ width: 100, height: 36, borderRadius: 'var(--radius-md)' }} />
      <div className="skeleton" style={{ width: 140, height: 14, borderRadius: 'var(--radius-sm)' }} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
        {[1, 2, 3].map((i) => (
          <div key={i} className="skeleton" style={{ width: '100%', height: 14, borderRadius: 'var(--radius-sm)' }} />
        ))}
      </div>
      <div className="skeleton" style={{ width: '100%', height: 40, borderRadius: 'var(--radius-md)', marginTop: 8 }} />
    </div>
  )
}

function PackageCardSkeleton() {
  return (
    <div className="card" style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="skeleton" style={{ width: 80, height: 18, borderRadius: 'var(--radius-sm)' }} />
      <div className="skeleton" style={{ width: 120, height: 28, borderRadius: 'var(--radius-md)' }} />
      <div className="skeleton" style={{ width: '100%', height: 36, borderRadius: 'var(--radius-md)' }} />
    </div>
  )
}

function SubscriptionBannerSkeleton() {
  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div className="skeleton" style={{ width: 40, height: 40, borderRadius: 'var(--radius-full)' }} />
        <div style={{ flex: 1 }}>
          <div className="skeleton" style={{ width: 120, height: 16, borderRadius: 'var(--radius-sm)', marginBottom: 8 }} />
          <div className="skeleton" style={{ width: 200, height: 12, borderRadius: 'var(--radius-sm)' }} />
        </div>
        <div className="skeleton" style={{ width: 80, height: 36, borderRadius: 'var(--radius-md)' }} />
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Subscription Status Banner
   ═══════════════════════════════════════════════════════════════════════════ */

function SubscriptionBanner({
  subscription,
  plan,
  onRenew,
  onCancel,
  busy,
}: {
  subscription: Subscription | null
  plan: Plan | null
  onRenew: () => void
  onCancel: () => void
  busy: boolean
}) {
  if (!subscription || !plan) return null

  const isActive = subscription.status === 'active' || subscription.status === 'trialing'
  const expiryDate = subscription.expires_at
    ? new Date(subscription.expires_at).toLocaleDateString('fa-IR', { year: 'numeric', month: 'long', day: 'numeric' })
    : null

  return (
    <div
      style={{
        background: isActive
          ? 'linear-gradient(135deg, rgba(52,211,153,0.08) 0%, rgba(124,111,247,0.06) 100%)'
          : 'var(--bg-surface)',
        border: `1px solid ${isActive ? 'rgba(52,211,153,0.2)' : 'var(--border)'}`,
        borderRadius: 'var(--radius-lg)',
        padding: '16px 20px',
        marginBottom: 32,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        flexWrap: 'wrap',
      }}
    >
      <div
        style={{
          width: 40,
          height: 40,
          borderRadius: 'var(--radius-full)',
          background: isActive ? 'rgba(52,211,153,0.15)' : 'var(--bg-hover)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <Icon name={isActive ? 'check' : 'info'} size={20} style={{ color: isActive ? 'var(--positive)' : 'var(--text-muted)' }} />
      </div>

      <div style={{ flex: 1, minWidth: 200 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>
          اشتراک فعال: پلن {plan.name_fa}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          {isActive && expiryDate ? `تاریخ انقضا: ${expiryDate}` : `وضعیت: ${subscription.status === 'active' ? 'فعال' : subscription.status}`}
          {plan.priority_queue && <span style={{ marginRight: 8, color: 'var(--accent)' }}>• اولویت در صف</span>}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
        {isActive && (
          <button
            className="btn btn-sm btn-secondary"
            onClick={onRenew}
            disabled={busy}
            style={{ fontSize: 12 }}
          >
            <Icon name="refresh" size={14} />
            تمدید
          </button>
        )}
        <button
          className="btn btn-sm btn-secondary"
          onClick={onCancel}
          disabled={busy}
          style={{ fontSize: 12, color: 'var(--danger)', borderColor: 'rgba(248,113,113,0.2)' }}
        >
          <Icon name="close" size={14} />
          لغو
        </button>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   FAQ Data
   ═══════════════════════════════════════════════════════════════════════════ */

const faqItems = [
  {
    q: 'آیا می‌توانم پلن خود را ارتقا یا کاهش دهم؟',
    a: 'بله، شما در هر زمان می‌توانید پلن خود را تغییر دهید. در صورت ارتقا، تفاوت مبلغ بر اساس زمان باقی‌مانده محاسبه می‌شود. در صورت کاهش پلن، تغییرات از دوره بعدی اعمال خواهد شد.',
  },
  {
    q: 'توکن‌های استفاده نشده در پایان ماه منتقل می‌شوند؟',
    a: 'توکن‌های باقی‌مانده در پایان هر دوره اشتراک منتقل نمی‌شوند. اما پلن نامحدود بدون محدودیت توکن است و نیازی به نگرانی درباره اتمام توکن نخواهید داشت.',
  },
  {
    q: 'آیا امکان استفاده رایگان وجود دارد؟',
    a: 'بله! پلن رایگان با ۳ میلیون توکن ماهانه و دسترسی به مدل‌های اقتصادی ارائه می‌شود. همچنین می‌توانید بسته‌های اعتباری خریداری کنید.',
  },
  {
    q: 'روش‌های پرداخت پشتیبانی شده کدامند؟',
    a: 'ما کلیه کارت‌های بانکی عضو شتاب، کیف پول دیجیتال و درگاه‌های پرداخت اینترنتی معتبر را پشتیبانی می‌کنیم. پرداخت‌ها از طریق درگاه‌های امن بانکی انجام می‌شود.',
  },
]

/* ═══════════════════════════════════════════════════════════════════════════
   Main Page
   ═══════════════════════════════════════════════════════════════════════════ */

export default function PricingPage() {
  const { token, user, loading: authLoading } = useAuth()

  // Data
  const [plans, setPlans] = useState<Plan[]>([])
  const [creditPackages, setCreditPackages] = useState<CreditPackage[]>([])
  const [subscription, setSubscription] = useState<Subscription | null>(null)
  const [currentPlan, setCurrentPlan] = useState<Plan | null>(null)

  // UI state
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null) // busy plan_id or package_id
  const [expandedFaq, setExpandedFaq] = useState<number | null>(null)

  /* ── Fetch plans ─────────────────────────────────────────────────────── */
  const fetchPlans = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/plans')
      if (res.ok) {
        const data = await res.json()
        setPlans(data.plans || [])
        setCreditPackages(data.credit_packages || [])
      }
    } catch {
      toast('خطا در دریافت اطلاعات پلن‌ها', 'error')
    } finally {
      setLoading(false)
    }
  }, [])

  /* ── Fetch subscription ──────────────────────────────────────────────── */
  const fetchSubscription = useCallback(async () => {
    if (!token) return
    try {
      const res = await fetch('/api/subscription', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setSubscription(data.subscription || null)
        setCurrentPlan(data.plan || null)
      }
    } catch {
      // silent
    }
  }, [token])

  useEffect(() => {
    fetchPlans()
  }, [fetchPlans])

  useEffect(() => {
    if (!authLoading) fetchSubscription()
  }, [authLoading, fetchSubscription])

  /* ── Subscribe to plan ───────────────────────────────────────────────── */
  const handleSubscribe = async (planId: string) => {
    if (!token) {
      window.location.href = '/login'
      return
    }
    setBusy(planId)
    try {
      const res = await fetch('/api/subscription/checkout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_id: planId }),
      })
      const data = await res.json()
      if (res.ok && data.url) {
        toast('در حال انتقال به درگاه پرداخت...', 'info')
        window.location.href = data.url
      } else if (res.ok) {
        toast('اشتراک با موفقیت فعال شد', 'success')
        fetchSubscription()
      } else {
        toast(data.detail || 'خطا در خرید اشتراک', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setBusy(null)
    }
  }

  /* ── Buy credit package ──────────────────────────────────────────────── */
  const handleBuyPackage = async (packageId: string) => {
    if (!token) {
      window.location.href = '/login'
      return
    }
    setBusy(packageId)
    try {
      const res = await fetch('/api/credit-package/checkout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ package_id: packageId }),
      })
      const data = await res.json()
      if (res.ok && data.url) {
        toast('در حال انتقال به درگاه پرداخت...', 'info')
        window.location.href = data.url
      } else if (res.ok) {
        toast('بسته با موفقیت خریداری شد', 'success')
      } else {
        toast(data.detail || 'خطا در خرید بسته', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setBusy(null)
    }
  }

  /* ── Cancel subscription ─────────────────────────────────────────────── */
  const handleCancel = async () => {
    if (!token || !subscription) return
    if (!confirm('آیا از لغو اشتراک اطمینان دارید؟')) return
    setBusy('cancel')
    try {
      const res = await fetch('/api/subscription/cancel', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await res.json()
      if (res.ok) {
        toast('اشتراک لغو شد', 'success')
        setSubscription(null)
        setCurrentPlan(null)
      } else {
        toast(data.detail || 'خطا در لغو اشتراک', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setBusy(null)
    }
  }

  /* ── Renew subscription ──────────────────────────────────────────────── */
  const handleRenew = async () => {
    if (!token || !subscription) return
    setBusy('renew')
    try {
      const res = await fetch('/api/subscription/renew', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await res.json()
      if (res.ok && data.url) {
        toast('در حال انتقال به درگاه پرداخت...', 'info')
        window.location.href = data.url
      } else if (res.ok) {
        toast('اشتراک تمدید شد', 'success')
        fetchSubscription()
      } else {
        toast(data.detail || 'خطا در تمدید اشتراک', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setBusy(null)
    }
  }

  /* ── Determine if a plan is current ──────────────────────────────────── */
  const isCurrentPlan = (planId: string) => {
    if (!subscription || !currentPlan) return false
    return currentPlan.id === planId && (subscription.status === 'active' || subscription.status === 'trialing')
  }

  /* ── Loading skeleton ────────────────────────────────────────────────── */
  if (loading) {
    return (
      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '32px 20px' }}>
        {/* Hero skeleton */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div className="skeleton" style={{ width: 260, height: 32, borderRadius: 'var(--radius-md)', margin: '0 auto 12px' }} />
          <div className="skeleton" style={{ width: 340, height: 16, borderRadius: 'var(--radius-sm)', margin: '0 auto' }} />
        </div>
        {/* Plan cards skeleton */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16, marginBottom: 48 }}>
          {[1, 2, 3, 4].map((i) => (
            <PlanCardSkeleton key={i} />
          ))}
        </div>
        {/* Packages skeleton */}
        <div className="skeleton" style={{ width: 180, height: 24, borderRadius: 'var(--radius-md)', margin: '0 auto 20px' }} />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginBottom: 48 }}>
          {[1, 2, 3, 4].map((i) => (
            <PackageCardSkeleton key={i} />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '32px 20px 64px' }}>

      {/* ═══════════════════════════════════════════════════════════════════
         Subscription Status Banner
         ═══════════════════════════════════════════════════════════════════ */}
      {!authLoading && user && subscription && (
        <SubscriptionBanner
          subscription={subscription}
          plan={currentPlan}
          onRenew={handleRenew}
          onCancel={handleCancel}
          busy={busy === 'cancel' || busy === 'renew'}
        />
      )}

      {/* ═══════════════════════════════════════════════════════════════════
         Hero Section
         ═══════════════════════════════════════════════════════════════════ */}
      <div style={{ textAlign: 'center', marginBottom: 48 }}>
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '6px 16px',
            borderRadius: 'var(--radius-full)',
            background: 'var(--accent-dim)',
            marginBottom: 20,
          }}
        >
          <Icon name="sparkles" size={16} style={{ color: 'var(--accent)' }} />
          <span style={{ fontSize: 13, color: 'var(--accent)', fontWeight: 600 }}>پلن‌ها و قیمت‌ها</span>
        </div>
        <h1
          style={{
            fontSize: 32,
            fontWeight: 700,
            color: 'var(--text-primary)',
            marginBottom: 12,
            lineHeight: 1.4,
          }}
        >
          پلن مناسب خودت رو انتخاب کن
        </h1>
        <p
          style={{
            fontSize: 15,
            color: 'var(--text-secondary)',
            maxWidth: 520,
            margin: '0 auto',
            lineHeight: 1.7,
          }}
        >
          از پلن رایگان شروع کن و هر زمان که خواستی ارتقا بده. همه پلن‌ها شامل پشتیبانی و بروزرسانی رایگان هستند.
        </p>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════
         Subscription Plans Grid
         ═══════════════════════════════════════════════════════════════════ */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: 16,
          marginBottom: 56,
        }}
      >
        {plans.map((plan) => {
          const colors = planColors[plan.id] || planColors.free
          const isPopular = plan.id === 'pro'
          const isUnlimited = plan.id === 'unlimited'
          const isFree = plan.id === 'free'
          const isCurrent = isCurrentPlan(plan.id)

          return (
            <div
              key={plan.id}
              style={{
                background: colors.bg,
                border: `1.5px solid ${colors.border}`,
                borderRadius: 'var(--radius-lg)',
                padding: 28,
                display: 'flex',
                flexDirection: 'column',
                position: 'relative',
                transition: 'transform 0.2s ease, box-shadow 0.2s ease',
                boxShadow: isUnlimited ? '0 0 30px rgba(124,111,247,0.1)' : 'none',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-2px)'
                if (isUnlimited || isPopular) {
                  e.currentTarget.style.boxShadow = '0 0 30px rgba(124,111,247,0.15)'
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)'
                if (isUnlimited) {
                  e.currentTarget.style.boxShadow = '0 0 30px rgba(124,111,247,0.1)'
                } else {
                  e.currentTarget.style.boxShadow = 'none'
                }
              }}
            >
              {/* Popular badge */}
              {isPopular && (
                <div
                  style={{
                    position: 'absolute',
                    top: -12,
                    left: '50%',
                    transform: 'translateX(-50%)',
                    background: 'var(--accent)',
                    color: '#fff',
                    fontSize: 11,
                    fontWeight: 600,
                    padding: '4px 14px',
                    borderRadius: 'var(--radius-full)',
                    whiteSpace: 'nowrap',
                    boxShadow: '0 2px 8px rgba(124,111,247,0.3)',
                  }}
                >
                  ⭐ محبوب‌ترین
                </div>
              )}

              {/* Unlimited glow effect */}
              {isUnlimited && (
                <div
                  style={{
                    position: 'absolute',
                    inset: -1,
                    borderRadius: 'var(--radius-lg)',
                    background: 'linear-gradient(135deg, var(--accent) 0%, #67e8f9 50%, var(--accent) 100%)',
                    opacity: 0.15,
                    zIndex: -1,
                    filter: 'blur(1px)',
                  }}
                />
              )}

              {/* Plan name */}
              <div style={{ fontSize: 13, color: colors.accent, fontWeight: 600, marginBottom: 8 }}>
                پلن {plan.name_fa}
              </div>

              {/* Price */}
              <div style={{ marginBottom: 4 }}>
                {plan.price_monthly === 0 ? (
                  <span style={{ fontSize: 32, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>
                    رایگان
                  </span>
                ) : (
                  <>
                    <span
                      style={{
                        fontSize: 32,
                        fontWeight: 700,
                        color: 'var(--text-primary)',
                        fontFeatureSettings: '"tnum"',
                      }}
                    >
                      {fmtIRR(plan.price_monthly)}
                    </span>
                    <span style={{ fontSize: 13, color: 'var(--text-muted)', marginRight: 4 }}>/ماه</span>
                  </>
                )}
              </div>

              {/* Token quota */}
              <div
                style={{
                  fontSize: 13,
                  color: plan.monthly_token_quota === 0 ? 'var(--accent)' : 'var(--text-secondary)',
                  fontWeight: plan.monthly_token_quota === 0 ? 600 : 400,
                  marginBottom: 20,
                  fontFeatureSettings: '"tnum"',
                }}
              >
                {formatTokens(plan.monthly_token_quota)}
                {plan.daily_token_limit > 0 && (
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginTop: 2 }}>
                    سقف روزانه: {fmtIRR(plan.daily_token_limit)} توکن
                  </span>
                )}
              </div>

              <div className="divider" style={{ marginBottom: 16 }} />

              {/* Features */}
              <ul style={{ listStyle: 'none', padding: 0, margin: 0, flex: 1 }}>
                {plan.features.map((feature) => (
                  <li
                    key={feature}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 8,
                      fontSize: 13,
                      color: 'var(--text-secondary)',
                      marginBottom: 10,
                      lineHeight: 1.5,
                    }}
                  >
                    <Icon
                      name="check"
                      size={16}
                      style={{
                        color: 'var(--positive)',
                        flexShrink: 0,
                        marginTop: 2,
                      }}
                    />
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>

              {/* CTA Button */}
              <button
                className={`btn ${isFree ? 'btn-secondary' : 'btn-primary'}`}
                style={{
                  width: '100%',
                  marginTop: 16,
                  padding: '10px 16px',
                  fontSize: 14,
                  fontWeight: 600,
                  borderRadius: 'var(--radius-md)',
                  ...(isCurrent
                    ? {
                        background: 'var(--bg-hover)',
                        color: 'var(--text-muted)',
                        borderColor: 'var(--border)',
                        cursor: 'default',
                        opacity: 0.7,
                      }
                    : {}),
                }}
                disabled={isCurrent || busy === plan.id}
                onClick={() => handleSubscribe(plan.id)}
              >
                {isCurrent ? (
                  'پلن فعلی'
                ) : busy === plan.id ? (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <Icon name="refresh" size={14} className="spin" />
                    در حال پردازش...
                  </span>
                ) : isFree ? (
                  'شروع رایگان'
                ) : isUnlimited ? (
                  'شروع نامحدود'
                ) : (
                  'خرید اشتراک'
                )}
              </button>
            </div>
          )
        })}
      </div>

      {/* ═══════════════════════════════════════════════════════════════════
         Credit Packages Section
         ═══════════════════════════════════════════════════════════════════ */}
      {creditPackages.length > 0 && (
        <div style={{ marginBottom: 56 }}>
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '6px 16px',
                borderRadius: 'var(--radius-full)',
                background: 'rgba(251,191,36,0.1)',
                marginBottom: 16,
              }}
            >
              <Icon name="gift" size={16} style={{ color: 'var(--warning)' }} />
              <span style={{ fontSize: 13, color: 'var(--warning)', fontWeight: 600 }}>بسته‌های اعتباری</span>
            </div>
            <h2 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>
              بسته اعتباری بخر، ارزون‌تر استفاده کن!
            </h2>
            <p style={{ fontSize: 14, color: 'var(--text-secondary)', maxWidth: 460, margin: '0 auto' }}>
              با خرید بسته‌های اعتباری، درصد بیشتری اعتبار هدیه بگیر و ارزان‌تر از هوش مصنوعی استفاده کن.
            </p>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: 16,
            }}
          >
            {creditPackages.map((pkg) => {
              const hasBonus = pkg.bonus_percent > 0

              return (
                <div
                  key={pkg.id}
                  style={{
                    background: hasBonus ? 'var(--bg-surface)' : 'var(--bg-surface)',
                    border: hasBonus ? '1.5px solid rgba(251,191,36,0.3)' : '1px solid var(--border)',
                    borderRadius: 'var(--radius-lg)',
                    padding: 24,
                    display: 'flex',
                    flexDirection: 'column',
                    position: 'relative',
                    transition: 'transform 0.2s ease',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-2px)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'translateY(0)'
                  }}
                >
                  {/* Bonus badge */}
                  {hasBonus && (
                    <div
                      style={{
                        position: 'absolute',
                        top: 12,
                        left: 12,
                        background: 'rgba(251,191,36,0.15)',
                        color: 'var(--warning)',
                        fontSize: 11,
                        fontWeight: 600,
                        padding: '3px 10px',
                        borderRadius: 'var(--radius-full)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      <Icon name="gift" size={12} />
                      +{pkg.bonus_percent}% هدیه
                    </div>
                  )}

                  {/* Package name */}
                  <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>
                    {pkg.name_fa}
                  </div>

                  {/* Base amount */}
                  <div style={{ marginBottom: 4 }}>
                    <span
                      style={{
                        fontSize: 24,
                        fontWeight: 700,
                        color: 'var(--text-primary)',
                        fontFeatureSettings: '"tnum"',
                      }}
                    >
                      {fmtIRR(pkg.base_amount)}
                    </span>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)', marginRight: 4 }}>تومان</span>
                  </div>

                  {/* Total credits */}
                  <div
                    style={{
                      fontSize: 13,
                      color: hasBonus ? 'var(--positive)' : 'var(--text-secondary)',
                      fontWeight: hasBonus ? 600 : 400,
                      marginBottom: 16,
                      fontFeatureSettings: '"tnum"',
                    }}
                  >
                    مبلغ دریافتی: {fmtIRR(pkg.total_credits)} تومان
                    {hasBonus && (
                      <span style={{ fontSize: 11, color: 'var(--warning)', display: 'block', marginTop: 2 }}>
                        ({pkg.bonus_percent}% هدیه اضافه)
                      </span>
                    )}
                  </div>

                  <div className="divider" style={{ marginBottom: 16 }} />

                  {/* Buy button */}
                  <button
                    className="btn btn-secondary"
                    style={{
                      width: '100%',
                      marginTop: 'auto',
                      padding: '10px 16px',
                      fontSize: 14,
                      fontWeight: 600,
                      borderRadius: 'var(--radius-md)',
                      ...(hasBonus ? { borderColor: 'rgba(251,191,36,0.3)', color: 'var(--warning)' } : {}),
                    }}
                    disabled={busy === pkg.id}
                    onClick={() => handleBuyPackage(pkg.id)}
                  >
                    {busy === pkg.id ? (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                        <Icon name="refresh" size={14} className="spin" />
                        در حال پردازش...
                      </span>
                    ) : (
                      'خرید بسته'
                    )}
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════
         FAQ Section
         ═══════════════════════════════════════════════════════════════════ */}
      <div style={{ maxWidth: 680, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <h2 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>
            سوالات متداول
          </h2>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
            پاسخ سوالات رایج شما درباره پلن‌ها و قیمت‌ها
          </p>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {faqItems.map((item, idx) => {
            const isExpanded = expandedFaq === idx
            return (
              <div
                key={idx}
                style={{
                  background: 'var(--bg-surface)',
                  border: `1px solid ${isExpanded ? 'var(--border-strong)' : 'var(--border)'}`,
                  borderRadius: 'var(--radius-md)',
                  overflow: 'hidden',
                  transition: 'border-color 0.2s ease',
                }}
              >
                <button
                  onClick={() => setExpandedFaq(isExpanded ? null : idx)}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '14px 18px',
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--text-primary)',
                    fontSize: 14,
                    fontWeight: 600,
                    textAlign: 'right',
                    cursor: 'pointer',
                    gap: 12,
                  }}
                >
                  <span>{item.q}</span>
                  <Icon
                    name="arrowRight"
                    size={18}
                    style={{
                      color: 'var(--text-muted)',
                      transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                      transition: 'transform 0.2s ease',
                      flexShrink: 0,
                    }}
                  />
                </button>
                <div
                  style={{
                    maxHeight: isExpanded ? 200 : 0,
                    overflow: 'hidden',
                    transition: 'max-height 0.3s ease',
                  }}
                >
                  <div
                    style={{
                      padding: '0 18px 14px',
                      fontSize: 13,
                      color: 'var(--text-secondary)',
                      lineHeight: 1.8,
                    }}
                  >
                    {item.a}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════
         Bottom CTA
         ═══════════════════════════════════════════════════════════════════ */}
      <div
        style={{
          textAlign: 'center',
          marginTop: 56,
          padding: '40px 24px',
          background: 'linear-gradient(135deg, rgba(124,111,247,0.08) 0%, rgba(103,232,249,0.04) 100%)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border)',
        }}
      >
        <Icon name="sparkles" size={28} style={{ color: 'var(--accent)', marginBottom: 12 }} />
        <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>
          سوالی دارید؟
        </h3>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 20, maxWidth: 400, margin: '0 auto 20px' }}>
          تیم پشتیبانی ما آماده کمک به شماست. هر سوالی دارید بپرسید.
        </p>
        <a
          href="/chat"
          className="btn btn-primary"
          style={{
            padding: '10px 28px',
            fontSize: 14,
            fontWeight: 600,
            borderRadius: 'var(--radius-md)',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <Icon name="chat" size={16} />
          شروع چت رایگان
        </a>
      </div>
    </div>
  )
}
