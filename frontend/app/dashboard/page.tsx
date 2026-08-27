'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { planBadgeClass } from './types'
import { dashboardPageStrings } from './page.strings'
import { useDashboardData } from './hooks/useDashboardData'
import { usePaymentBanner } from './hooks/usePaymentBanner'
import { useBillingSettings } from './hooks/useBillingSettings'
import { StatCard } from './components/StatCard'
import { PaymentBanner } from './components/PaymentBanner'
import { UnauthenticatedView } from './components/UnauthenticatedView'
import { DashboardLoadingSkeleton } from './components/DashboardLoadingSkeleton'
import { PackagesCard } from './components/PackagesCard'
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
  const lang = useLang()
  const s = dashboardPageStrings(lang)

  const {
    profile,
    usage,
    balance,
    ledger,
    models,
    loading,
    refreshing,
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
  // name. A generic noun is less wrong than a wrong name.
  const displayName = profile?.username || s.defaultUser
  const plan = profile?.plan || 'free'
  const recentLedger = ledger.slice(0, 10)

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
            {s.greeting(displayName)}
          </h1>
          <p className="page-subtitle">
            {s.subtitle}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className={planBadgeClass[plan] || 'badge'}>
            {s.planLabels[plan] || plan}
          </span>
          <button
            className="btn btn-sm"
            onClick={() => fetchData(true)}
            disabled={refreshing}
            title={s.refresh}
            style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}
          >
            <span className={refreshing ? 'animate-spin' : ''}>
              <Icon name="refresh" size={14} />
            </span>
            {s.refresh}
          </button>
        </div>
      </header>

      {/* ─── Stat row: four equal columns across the full measure ─── */}
      <div className="dash-span-3">
        <StatCard icon="wallet" label={s.statBalance} value={balance ?? 0} unit={s.unitToman} lead />
      </div>
      <div className="dash-span-3">
        <StatCard icon="payment" label={s.statSpent} value={usage?.total_spent_this_month ?? 0} unit={s.unitToman} />
      </div>
      <div className="dash-span-3">
        <StatCard icon="chat" label={s.statConversations} value={usage?.event_count_this_month ?? 0} unit={s.unitConversation} />
      </div>
      <div className="dash-span-3">
        <StatCard icon="code" label={s.statTokens} value={usage?.total_input_tokens_this_month ?? 0} unit={s.unitToken} />
      </div>

      {/* ─── Packages + activity row ─── */}
      <PackagesCard
        balance={balance}
        onManagePackages={() => router.push('/pricing#credit-packages')}
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
