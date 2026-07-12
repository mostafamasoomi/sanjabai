'use client'

import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'

// ─── Types ──────────────────────────────────────────────────────────────────
type LedgerEntry = {
  id: number
  amount: number
  balance_after: number
  reason: string
  created_at: string
}

type PaymentRecord = {
  id: number
  amount: number
  status: string
  created_at: string
}

type LedgerFilter = 'all' | 'credit' | 'debit'

// ─── Constants ──────────────────────────────────────────────────────────────
const PRESET_AMOUNTS = [
  { label: '۱۰۰ هزار', value: 100_000 },
  { label: '۵۰۰ هزار', value: 500_000 },
  { label: '۱ میلیون', value: 1_000_000 },
  { label: '۵ میلیون', value: 5_000_000 },
]

const MIN_TOPUP = 10_000
const MAX_TOPUP = 100_000_000_000

// ─── Helpers ────────────────────────────────────────────────────────────────
const fmtIRR = (n: number) => n.toLocaleString('fa-IR')
const fmtToman = (n: number) => `${(n / 10).toLocaleString('fa-IR')} تومان`
const fmtDate = (s: string) =>
  new Date(s).toLocaleDateString('fa-IR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })

const statusLabel: Record<string, { text: string; badge: string }> = {
  paid: { text: 'موفق', badge: 'badge-positive' },
  success: { text: 'موفق', badge: 'badge-positive' },
  pending: { text: 'در انتظار', badge: 'badge-warning' },
  failed: { text: 'ناموفق', badge: 'badge-danger' },
  cancelled: { text: 'لغو شده', badge: 'badge-danger' },
}

// ─── Skeleton Components ────────────────────────────────────────────────────
function BalanceSkeleton() {
  return (
    <div className="card wallet-balance-card" style={{ minHeight: 200 }}>
      <div className="skeleton" style={{ width: 100, height: 14, borderRadius: 'var(--radius-sm)', marginBottom: 16 }} />
      <div className="skeleton" style={{ width: 260, height: 48, borderRadius: 'var(--radius-md)', marginBottom: 12 }} />
      <div className="skeleton" style={{ width: 140, height: 14, borderRadius: 'var(--radius-sm)' }} />
    </div>
  )
}

function TopupSkeleton() {
  return (
    <div className="card" style={{ minHeight: 200 }}>
      <div className="skeleton" style={{ width: 80, height: 14, borderRadius: 'var(--radius-sm)', marginBottom: 16 }} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="skeleton" style={{ height: 48, borderRadius: 'var(--radius-md)' }} />
        ))}
      </div>
      <div className="skeleton" style={{ width: '100%', height: 44, borderRadius: 'var(--radius-md)', marginTop: 12 }} />
    </div>
  )
}

function TableSkeleton() {
  return (
    <div className="card">
      <div className="skeleton" style={{ width: 120, height: 18, borderRadius: 'var(--radius-sm)', marginBottom: 20 }} />
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
          <div className="skeleton" style={{ flex: 1, height: 16, borderRadius: 'var(--radius-sm)' }} />
          <div className="skeleton" style={{ width: 80, height: 16, borderRadius: 'var(--radius-sm)' }} />
          <div className="skeleton" style={{ width: 100, height: 16, borderRadius: 'var(--radius-sm)' }} />
        </div>
      ))}
    </div>
  )
}

// ─── Empty State ────────────────────────────────────────────────────────────
function EmptyStateIcon({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div className="wallet-empty-state">
      <div className="wallet-empty-icon-wrap">
        <Icon name={icon as any} size={28} style={{ color: 'var(--accent)' }} />
      </div>
      <p style={{ color: 'var(--text-secondary)', fontWeight: 600, marginBottom: 4, fontSize: 15 }}>{title}</p>
      <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>{desc}</p>
    </div>
  )
}

// ─── Main Page ──────────────────────────────────────────────────────────────
export default function WalletPage() {
  const { token, user, loading: authLoading } = useAuth()

  // Data state
  const [balance, setBalance] = useState<number | null>(null)
  const [ledger, setLedger] = useState<LedgerEntry[]>([])
  const [payments, setPayments] = useState<PaymentRecord[]>([])

  // UI state
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [topupAmount, setTopupAmount] = useState('')
  const [selectedPreset, setSelectedPreset] = useState<number | null>(100_000)
  const [ledgerFilter, setLedgerFilter] = useState<LedgerFilter>('all')
  const [showConfirm, setShowConfirm] = useState(false)
  const [copied, setCopied] = useState(false)

  // ── Data fetching ────────────────────────────────────────────────────────
  const fetchData = useCallback(
    async (silent = false) => {
      if (!token) return
      if (!silent) setLoading(true)
      else setRefreshing(true)

      const headers = { Authorization: `Bearer ${token}` }
      try {
        const [walletRes, ledgerRes, payRes] = await Promise.all([
          fetch('/api/wallet', { headers }),
          fetch('/api/wallet/ledger', { headers }),
          fetch('/api/payment/history', { headers }),
        ])
        const [wallet, ledgerData, payData] = await Promise.all([
          walletRes.ok ? walletRes.json() : null,
          ledgerRes.ok ? ledgerRes.json() : null,
          payRes.ok ? payRes.json() : null,
        ])
        if (wallet) setBalance(wallet.balance ?? 0)
        if (ledgerData) setLedger(Array.isArray(ledgerData) ? ledgerData : [])
        if (payData) setPayments(Array.isArray(payData) ? payData : [])
      } catch {
        if (!silent) toast('خطا در دریافت اطلاعات', 'error')
      } finally {
        setLoading(false)
        setRefreshing(false)
      }
    },
    [token],
  )

  useEffect(() => {
    if (!token) {
      setLoading(false)
      return
    }
    fetchData()
  }, [token, fetchData])

  // ── Topup logic ──────────────────────────────────────────────────────────
  const effectiveAmount = (selectedPreset ?? parseInt(topupAmount)) || 0

  const handlePreset = (val: number) => {
    setSelectedPreset(val)
    setTopupAmount('')
  }

  const handleCustomAmount = (v: string) => {
    setSelectedPreset(null)
    setTopupAmount(v)
  }

  const initiateTopup = () => {
    const amount = effectiveAmount
    if (!amount || amount < MIN_TOPUP) return toast(`حداقل مبلغ شارژ ${fmtIRR(MIN_TOPUP)} ریال است`, 'error')
    if (amount > MAX_TOPUP) return toast(`حداکثر مبلغ شارژ ${fmtIRR(MAX_TOPUP)} ریال است`, 'error')
    setShowConfirm(true)
  }

  const confirmTopup = async () => {
    if (!token) return
    setShowConfirm(false)
    setBusy(true)
    try {
      const res = await fetch('/api/wallet/topup', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: effectiveAmount }),
      })
      const data = await res.json()
      if (res.ok && data.payment_url) {
        toast('در حال انتزار به درگاه پرداخت...', 'info')
        window.location.href = data.payment_url
      } else if (res.ok) {
        setBalance(data.balance_after ?? balance)
        setLedger((prev) => [
          {
            id: Date.now(),
            amount: effectiveAmount,
            balance_after: data.balance_after ?? 0,
            reason: 'شارژ حساب',
            created_at: new Date().toISOString(),
          },
          ...prev,
        ])
        toast('شارژ با موفقیت انجام شد', 'success')
      } else {
        toast(data.detail || 'خطا در شارژ', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setBusy(false)
    }
  }

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
            <Icon name="wallet" size={32} style={{ color: 'var(--accent)' }} />
          </div>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>کیف پول</h2>
          <p style={{ color: 'var(--text-muted)', marginBottom: 24 }}>برای مشاهده کیف پول، ابتدا وارد حساب خود شوید.</p>
          <a href="/login" className="btn btn-lg btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            ورود
            <Icon name="arrowLeft" size={16} />
          </a>
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
            <Icon name="wallet" size={20} style={{ color: 'var(--accent)' }} />
          </div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>کیف پول</h1>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16, marginBottom: 24 }}>
          <BalanceSkeleton />
          <TopupSkeleton />
        </div>
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
            <Icon name="wallet" size={20} style={{ color: 'var(--accent)' }} />
          </div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>کیف پول</h1>
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

      {/* Balance + Topup grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16, marginBottom: 24 }}>
        {/* ── Balance Hero Card ─────────────────────────────────────── */}
        <div className="card wallet-balance-card">
          {/* Glow accent */}
          <div className="wallet-balance-glow" />

          <div style={{ position: 'relative' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <Icon name="wallet" size={14} style={{ color: 'var(--text-muted)' }} />
              <span style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 500 }}>موجودی فعلی</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 8, marginBottom: 4 }}>
              <span className="wallet-balance-amount">
                {fmtIRR(balance ?? 0)}
              </span>
              <span style={{ fontSize: 14, color: 'var(--text-muted)', fontWeight: 500 }}>ریال</span>
            </div>

            <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>
              <Icon name="payment" size={12} style={{ display: 'inline', verticalAlign: -2, marginRight: 4 }} />
              معادل {fmtToman(balance ?? 0)}
            </p>

            <div className="divider" style={{ margin: '12px 0' }} />

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button
                className={`btn btn-sm btn-secondary ${copied ? 'wallet-copy-success' : ''}`}
                onClick={copyBalance}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
              >
                <Icon name={copied ? 'check' : 'copy'} size={14} />
                {copied ? 'کپی شد' : 'کپی'}
              </button>
            </div>
          </div>
        </div>

        {/* ── Topup Card ───────────────────────────────────────────── */}
        <div className="card wallet-topup-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16 }}>
            <div className="wallet-topup-icon">
              <Icon name="plus" size={14} style={{ color: 'var(--accent)' }} />
            </div>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 600 }}>شارژ حساب</span>
          </div>

          {/* Preset buttons */}
          <div className="wallet-preset-grid">
            {PRESET_AMOUNTS.map((p) => (
              <button
                key={p.value}
                className={`wallet-preset-btn ${selectedPreset === p.value ? 'wallet-preset-active' : ''}`}
                onClick={() => handlePreset(p.value)}
              >
                {p.label}
                <span className="wallet-preset-sub">
                  {fmtIRR(p.value)} ریال
                </span>
              </button>
            ))}
          </div>

          {/* Custom amount input */}
          <div style={{ position: 'relative', marginBottom: 12 }}>
            <Icon
              name="payment"
              size={16}
              style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}
            />
            <input
              className="input"
              type="number"
              value={topupAmount}
              onChange={(e) => handleCustomAmount(e.target.value)}
              placeholder="مبلغ دلخواه (ریال)"
              min={MIN_TOPUP}
              max={MAX_TOPUP}
              style={{
                paddingRight: 36,
                fontFeatureSettings: '"tnum"',
                width: '100%',
              }}
            />
          </div>

          {effectiveAmount > 0 && effectiveAmount < MIN_TOPUP && (
            <p style={{ fontSize: 11, color: 'var(--danger)', marginBottom: 8 }}>
              حداقل مبلغ: {fmtIRR(MIN_TOPUP)} ریال
            </p>
          )}

          <button
            className="btn btn-lg btn-primary wallet-topup-btn"
            onClick={initiateTopup}
            disabled={busy || effectiveAmount <= 0}
            style={{
              width: '100%',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              opacity: busy || effectiveAmount <= 0 ? 0.5 : 1,
            }}
          >
            <Icon name="send" size={16} />
            {busy ? 'در حال پردازش...' : `شارژ ${effectiveAmount > 0 ? fmtIRR(effectiveAmount) + ' ریال' : 'حساب'}`}
          </button>
        </div>
      </div>

      {/* ── Ledger Section ─────────────────────────────────────────── */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Icon name="history" size={16} style={{ color: 'var(--accent)' }} />
            <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>تاریخچه تراکنشها</h2>
            <span className="badge badge-accent" style={{ marginLeft: 4 }}>{fmtIRR(ledger.length)}</span>
          </div>

          {/* Filter tabs */}
          <div className="wallet-filter-tabs">
            {([
              { key: 'all', label: 'همه' },
              { key: 'credit', label: 'واریز' },
              { key: 'debit', label: 'برداشت' },
            ] as const).map((f) => (
              <button
                key={f.key}
                onClick={() => setLedgerFilter(f.key)}
                className={`wallet-filter-tab ${ledgerFilter === f.key ? 'wallet-filter-active' : ''}`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {filteredLedger.length === 0 ? (
          <EmptyStateIcon
            icon="history"
            title="تراکنشی ثبت نشده"
            desc={ledgerFilter === 'all' ? 'هنوز هیچ تراکنشی انجام نشده است.' : 'تراکنشی با این فیلتر یافت نشد.'}
          />
        ) : (
          <div className="wallet-table-wrap">
            <table className="wallet-table">
              <thead>
                <tr>
                  <th>تاریخ</th>
                  <th>شرح</th>
                  <th style={{ textAlign: 'left' }}>مبلغ</th>
                  <th style={{ textAlign: 'left' }}>مانده</th>
                </tr>
              </thead>
              <tbody>
                {filteredLedger.map((l, idx) => {
                  const isCredit = l.amount > 0
                  return (
                    <tr key={l.id} className={idx % 2 === 0 ? 'wallet-row-even' : 'wallet-row-odd'}>
                      <td className="wallet-td-date">
                        {fmtDate(l.created_at)}
                      </td>
                      <td style={{ padding: '12px', color: 'var(--text-primary)', fontWeight: 500 }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                          <span className={`wallet-amount-dot ${isCredit ? 'positive' : 'negative'}`} />
                          {l.reason}
                        </span>
                      </td>
                      <td
                        className={`wallet-td-amount ${isCredit ? 'positive' : 'negative'}`}
                      >
                        {isCredit ? '+' : ''}{fmtIRR(l.amount)} <span className="wallet-currency">ریال</span>
                      </td>
                      <td className="wallet-td-balance">
                        {fmtIRR(l.balance_after)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Payment History Section ────────────────────────────────── */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16 }}>
          <Icon name="payment" size={16} style={{ color: 'var(--accent)' }} />
          <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>تاریخچه پرداختها</h2>
        </div>

        {payments.length === 0 ? (
          <EmptyStateIcon icon="payment" title="پرداختی ثبت نشده" desc="هنوز پرداختی انجام نشده است." />
        ) : (
          <div className="wallet-table-wrap">
            <table className="wallet-table">
              <thead>
                <tr>
                  <th>تاریخ</th>
                  <th>شناسه</th>
                  <th style={{ textAlign: 'left' }}>مبلغ</th>
                  <th>وضعیت</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((p, idx) => {
                  const st = statusLabel[p.status] || { text: p.status, badge: 'badge-warning' }
                  return (
                    <tr key={p.id} className={idx % 2 === 0 ? 'wallet-row-even' : 'wallet-row-odd'}>
                      <td className="wallet-td-date">
                        {fmtDate(p.created_at)}
                      </td>
                      <td style={{ padding: '12px', color: 'var(--text-secondary)', fontFeatureSettings: '"tnum"', fontSize: 12 }}>
                        #{p.id}
                      </td>
                      <td className="wallet-td-amount" style={{ color: 'var(--text-primary)' }}>
                        {fmtIRR(p.amount)} <span className="wallet-currency">ریال</span>
                      </td>
                      <td style={{ padding: '12px' }}>
                        <span className={`badge ${st.badge}`}>{st.text}</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Confirmation Modal ─────────────────────────────────────── */}
      {showConfirm && (
        <div className="wallet-modal-overlay" onClick={() => setShowConfirm(false)}>
          <div className="card wallet-modal-card" onClick={(e) => e.stopPropagation()}>
            <div style={{ textAlign: 'center', marginBottom: 20 }}>
              <div className="wallet-modal-icon">
                <Icon name="wallet" size={28} style={{ color: 'var(--accent)' }} />
              </div>
              <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>تایید شارژ</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginBottom: 4 }}>
                آیا از شارژ حساب به مبلغ
              </p>
              <p className="wallet-modal-amount">
                {fmtIRR(effectiveAmount)} ریال
              </p>
              <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>اطمینان دارید؟</p>
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <button
                className="btn btn-secondary"
                onClick={() => setShowConfirm(false)}
                style={{ flex: 1 }}
              >
                انصراف
              </button>
              <button
                className="btn btn-lg btn-primary"
                onClick={confirmTopup}
                disabled={busy}
                style={{ flex: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
              >
                <Icon name="check" size={16} />
                {busy ? 'در حال پردازش...' : 'تایید و پرداخت'}
              </button>
            </div>
          </div>
        </div>
      )}

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
