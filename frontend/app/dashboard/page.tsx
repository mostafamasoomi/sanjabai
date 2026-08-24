'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { planLabels, planBadgeClass } from './types'
import { useDashboardData } from './hooks/useDashboardData'
import { usePaymentBanner } from './hooks/usePaymentBanner'
import { useBillingSettings } from './hooks/useBillingSettings'
import { StatCard } from './components/StatCard'
import { PaymentBanner } from './components/PaymentBanner'
import { UnauthenticatedView } from './components/UnauthenticatedView'
import { DashboardLoadingSkeleton } from './components/DashboardLoadingSkeleton'
import { SubscriptionCard } from './components/SubscriptionCard'
import { RecentActivityCard } from './components/RecentActivityCard'
import { QuickActionsCard } from './components/QuickActionsCard'
import { AccountInfoCard } from './components/AccountInfoCard'
import { PaygSection } from './components/PaygSection'

/* ═══════════════════════════════════════════════════════════════
   Main Dashboard Page

   State/logic is split across hooks/ (data fetching, payment banner,
   billing settings) and components/ (stat cards, ledger rows, section
   cards) -- this file wires them together and owns only the page-wide
   layout and derived values.
   ═══════════════════════════════════════════════════════════════ */

export default function DashboardPage() {
  const { token, user, loading: authLoading } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()

  const {
    profile,
    usage,
    balance,
    ledger,
    models,
    loading,
    refreshing,
    subscription,
    subscriptionPlan,
    billingSettings,
    setBillingSettings,
    fetchData,
  } = useDashboardData(token, authLoading)

  const { paymentBanner, setPaymentBanner } = usePaymentBanner(searchParams)

  const {
    paygLoading,
    showHardLimitInput,
    setShowHardLimitInput,
    hardLimitValue,
    setHardLimitValue,
    hardLimitLoading,
    togglePayg,
    setHardLimit,
  } = useBillingSettings(token, billingSettings, setBillingSettings)

  /* ─── Not authenticated ─── */
  if (!authLoading && !user) {
    return <UnauthenticatedView onLogin={() => router.push('/login')} />
  }

  /* ─── Loading state ─── */
  if (authLoading || loading) {
    return <DashboardLoadingSkeleton />
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
      {/* ─── Payment-return banner ─── */}
      {paymentBanner && (
        <PaymentBanner banner={paymentBanner} onClose={() => setPaymentBanner(null)} />
      )}

      {/* ─── Header ─── */}
      <header className="dash-span-12" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
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
      <div className="dash-span-3">
        <StatCard icon="wallet" label="موجودی کیف پول" value={balance ?? 0} unit="تومان" lead />
      </div>
      <div className="dash-span-3">
        <StatCard icon="payment" label="کل هزینه" value={usage?.total_spent_this_month ?? 0} unit="تومان" />
      </div>
      <div className="dash-span-3">
        <StatCard icon="chat" label="تعداد مکالمات" value={usage?.event_count_this_month ?? 0} unit="مکالمه" />
      </div>
      <div className="dash-span-3">
        <StatCard icon="code" label="کل توکن‌ها" value={usage?.total_input_tokens_this_month ?? 0} unit="توکن" />
      </div>

      {/* ─── Subscription + activity row ─── */}
      <SubscriptionCard
        planName={planName}
        subStatusColor={subStatusColor}
        subStatusLabel={subStatusLabel}
        tokenQuota={tokenQuota}
        tokensUsed={tokensUsed}
        tokenPct={tokenPct}
        endsAt={subscription?.ends_at}
        onChangePlan={() => router.push('/pricing')}
      />

      <RecentActivityCard
        recentLedger={recentLedger}
        onViewAll={() => router.push('/wallet')}
        onTopUp={() => router.push('/wallet')}
      />

      {/* ─── Bottom row: three equal thirds ─── */}
      <QuickActionsCard
        modelCount={models.length}
        onChat={() => router.push('/chat')}
        onWallet={() => router.push('/wallet')}
        onModels={() => router.push('/models')}
        onCreditPackages={() => router.push('/pricing#credit-packages')}
        onBillingSettings={() => {
          const el = document.getElementById('payg-section')
          if (el) el.scrollIntoView({ behavior: 'smooth' })
        }}
      />

      <AccountInfoCard profile={profile} onManageAccount={() => router.push('/profile')} />

      <PaygSection
        billingSettings={billingSettings}
        paygLoading={paygLoading}
        togglePayg={togglePayg}
        showHardLimitInput={showHardLimitInput}
        setShowHardLimitInput={setShowHardLimitInput}
        hardLimitValue={hardLimitValue}
        setHardLimitValue={setHardLimitValue}
        hardLimitLoading={hardLimitLoading}
        setHardLimit={setHardLimit}
      />
    </div>
  )
}
