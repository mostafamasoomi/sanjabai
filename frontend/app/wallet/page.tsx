'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import EntitlementPanel from './components/EntitlementPanel'
import { BalanceSkeleton, TopupSkeleton, TableSkeleton, PackagesSkeleton } from './components/WalletSkeletons'
import { PaymentBanner } from './components/PaymentBanner'
import { BalanceCard } from './components/BalanceCard'
import { TopupCard } from './components/TopupCard'
import { CreditPackagesSection } from './components/CreditPackagesSection'
import { LedgerSection } from './components/LedgerSection'
import { PaymentHistorySection } from './components/PaymentHistorySection'
import { TopupConfirmModal } from './components/TopupConfirmModal'
import { useWalletData } from './hooks/useWalletData'
import { usePaymentBanner } from './hooks/usePaymentBanner'
import { useTopupFlow } from './hooks/useTopupFlow'
import type { LedgerFilter } from './walletTypes'

/* ═══════════════════════════════════════════════════════════════════════════
   Sanjabai Wallet
   Balance, top-up (preset/custom amount), credit-package purchase, ledger
   and payment history, and the payment-return banner. State/logic is split
   across hooks/ (data fetching, payment banner, top-up/purchase flow) and
   components/ (skeletons, balance card, topup card, section tables, modal)
   -- this file wires them together and owns only what's genuinely page-wide.
   ═══════════════════════════════════════════════════════════════════════════ */

export default function WalletPage() {
  const { token, user, loading: authLoading } = useAuth()

  const { balance, ledger, payments, creditPackages, modelOutputRates, loading, refreshing, fetchData } = useWalletData(token)
  const { paymentBanner, setPaymentBanner } = usePaymentBanner()
  const {
    busy,
    topupAmount,
    selectedPreset,
    showConfirm,
    setShowConfirm,
    purchasingPkgId,
    effectiveAmount,
    handlePreset,
    handleCustomAmount,
    initiateTopup,
    confirmTopup,
    handlePurchase,
  } = useTopupFlow(token)

  const [copied, setCopied] = useState(false)
  const [ledgerFilter, setLedgerFilter] = useState<LedgerFilter>('all')

  // ── Copy balance ─────────────────────────────────────────────────────────
  const copyBalance = () => {
    if (balance === null) return
    navigator.clipboard?.writeText(String(balance)).then(() => {
      setCopied(true)
      toast('موجودی کپی شد', 'success')
      setTimeout(() => setCopied(false), 2000)
    })
  }

  // ── Filtered ledger ──────────────────────────────────────────────────────
  const filteredLedger = ledger.filter((l) => {
    if (ledgerFilter === 'credit') return l.amount > 0
    if (ledgerFilter === 'debit') return l.amount < 0
    return true
  })

  // ── Auth gate ────────────────────────────────────────────────────────────
  if (authLoading) return null

  if (!user) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <div className="card" style={{ textAlign: 'center', padding: '48px 32px', maxWidth: 400 }}>
          <div className="wallet-empty-icon-wrap" style={{ marginBottom: 20 }}>
            <Icon name="wallet" size={32} className="text-accent" />
          </div>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>کیف پول</h2>
          <p style={{ color: 'var(--text-muted)', marginBottom: 24 }}>برای مشاهده کیف پول، ابتدا وارد حساب خود شوید.</p>
          <Link href="/login" className="btn btn-lg btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            ورود
            <Icon name="arrowLeft" size={16} />
          </Link>
        </div>
      </div>
    )
  }

  // ── Loading state ────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="wallet-page">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
          <div className="wallet-header-icon">
            <Icon name="wallet" size={20} className="text-accent" />
          </div>
          <h1 className="page-title">کیف پول</h1>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16, marginBottom: 24 }}>
          <BalanceSkeleton />
          <TopupSkeleton />
        </div>
        <PackagesSkeleton />
        <TableSkeleton />
      </div>
    )
  }

  // ── Main render ──────────────────────────────────────────────────────────
  return (
    <div className="wallet-page">
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div className="wallet-header-icon">
            <Icon name="wallet" size={20} className="text-accent" />
          </div>
          <h1 className="page-title">کیف پول</h1>
        </div>
        <button
          className="btn btn-sm btn-secondary"
          onClick={() => fetchData(true)}
          disabled={refreshing}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
          title="بروزرسانی"
        >
          <Icon name="refresh" size={14} className={refreshing ? 'spin' : ''} />
          بروزرسانی
        </button>
      </div>

      {/* Payment-return banner */}
      <PaymentBanner banner={paymentBanner} onClose={() => setPaymentBanner(null)} />

      {/* Balance + Topup grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16, marginBottom: 24 }}>
        <BalanceCard balance={balance} copied={copied} onCopy={copyBalance} />
        <TopupCard
          topupAmount={topupAmount}
          selectedPreset={selectedPreset}
          effectiveAmount={effectiveAmount}
          busy={busy}
          onPreset={handlePreset}
          onCustomAmount={handleCustomAmount}
          onInitiate={initiateTopup}
        />
      </div>

      <EntitlementPanel />

      <CreditPackagesSection
        creditPackages={creditPackages}
        purchasingPkgId={purchasingPkgId}
        modelOutputRates={modelOutputRates}
        onPurchase={handlePurchase}
      />

      <LedgerSection
        ledger={ledger}
        filteredLedger={filteredLedger}
        ledgerFilter={ledgerFilter}
        onFilterChange={setLedgerFilter}
      />

      <PaymentHistorySection payments={payments} />

      <TopupConfirmModal
        show={showConfirm}
        effectiveAmount={effectiveAmount}
        busy={busy}
        onCancel={() => setShowConfirm(false)}
        onConfirm={confirmTopup}
      />

      {/* ── Keyframes ──────────────────────────────────────────────── */}
      <style jsx global>{`
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .spin { animation: spin 1s linear infinite; }
      `}</style>
    </div>
  )
}
