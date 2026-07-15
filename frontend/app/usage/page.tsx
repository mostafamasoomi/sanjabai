'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════════════════════════════════ */

type ModelBreakdown = {
  model: string
  input_tokens: number
  output_tokens: number
  cost: number
  calls: number
}

type UsageEvent = {
  id: number
  model: string
  input_tokens: number
  output_tokens: number
  cost: number
  created_at: string | null
}

type UsageData = {
  current_balance: number
  total_spent_this_month: number
  total_input_tokens_this_month: number
  total_output_tokens_this_month: number
  event_count_this_month: number
  per_model_breakdown: ModelBreakdown[]
  recent_events: UsageEvent[]
}

/* ═══════════════════════════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════════════════════════ */

const fmtToman = (n: number) => `${n.toLocaleString('fa-IR')} تومان`
const fmtIRR = (n: number) => n.toLocaleString('fa-IR')
const fmtTokens = (n: number) => {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}
const fmtDate = (s: string | null) => {
  if (!s) return '-'
  return new Date(s).toLocaleDateString('fa-IR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const modelDisplayNames: Record<string, string> = {
  'agnes-2.0-flash': 'Agnes 2.0 Flash',
  'agnes-2.5-flash': 'Agnes 2.5 Flash',
  'gemini-3.5-flash': 'Gemini 3.5 Flash',
  'mimo-v2.5': 'MiMo V2.5',
  'mimo-v2.5-pro': 'MiMo V2.5 Pro',
  'mimo-v2.5-pro-ultraspeed': 'MiMo V2.5 Pro Ultra',
  'mistral-large': 'Mistral Large',
  'mistral-medium-3-5': 'Mistral Medium 3.5',
  'tencent-hy3': 'Tencent Hy3',
}

const modelColors = [
  '#7c6df7', '#67e8f9', '#f59e0b', '#34d399', '#f87171',
  '#e879f9', '#60a5fa', '#fbbf24', '#a78bfa',
]

/* ═══════════════════════════════════════════════════════════════════════════
   Skeleton
   ═══════════════════════════════════════════════════════════════════════════ */

function Skeleton({ width, height, style }: { width?: number | string; height?: number; style?: React.CSSProperties }) {
  return <div className="skeleton" style={{ width, height, borderRadius: 'var(--radius-sm)', ...style }} />
}

/* ═══════════════════════════════════════════════════════════════════════════
   Main Page
   ═══════════════════════════════════════════════════════════════════════════ */

export default function UsagePage() {
  const { token, user, loading: authLoading } = useAuth()
  const [data, setData] = useState<UsageData | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchUsage = useCallback(async (silent = false) => {
    if (!token) return
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      const res = await fetch('/api/usage', { headers: { Authorization: `Bearer ${token}` } })
      if (res.ok) {
        const d = await res.json()
        setData(d)
      } else {
        toast('خطا در دریافت اطلاعات مصرف', 'error')
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [token])

  useEffect(() => {
    if (!token) { setLoading(false); return }
    fetchUsage()
  }, [token, fetchUsage])

  if (authLoading) return null

  if (!user) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <div className="card" style={{ textAlign: 'center', padding: '48px 32px', maxWidth: 400 }}>
          <div style={{ width: 56, height: 56, borderRadius: 'var(--radius-full)', background: 'var(--accent-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px' }}>
            <Icon name="chart" size={28} style={{ color: 'var(--accent)' }} />
          </div>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>گزارش مصرف</h2>
          <p style={{ color: 'var(--text-muted)', marginBottom: 24 }}>برای مشاهده گزارش مصرف، ابتدا وارد حساب خود شوید.</p>
          <Link href="/login" className="btn btn-lg btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            ورود
            <Icon name="arrowLeft" size={16} />
          </Link>
        </div>
      </div>
    )
  }

  const totalTokens = (data?.total_input_tokens_this_month ?? 0) + (data?.total_output_tokens_this_month ?? 0)
  const maxModelCost = Math.max(...(data?.per_model_breakdown.map(m => m.cost) ?? [1]), 1)

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '32px 20px 64px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 'var(--radius-full)', background: 'var(--accent-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Icon name="chart" size={18} style={{ color: 'var(--accent)' }} />
          </div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>گزارش مصرف</h1>
        </div>
        <button
          className="btn btn-sm btn-secondary"
          onClick={() => fetchUsage(true)}
          disabled={refreshing}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
        >
          <Icon name="refresh" size={14} className={refreshing ? 'spin' : ''} />
          بروزرسانی
        </button>
      </div>

      {loading ? (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="card" style={{ padding: 20 }}>
                <Skeleton width={100} height={12} style={{ marginBottom: 12 }} />
                <Skeleton width={140} height={28} style={{ marginBottom: 8 }} />
                <Skeleton width={80} height={10} />
              </div>
            ))}
          </div>
          <div className="card" style={{ padding: 20 }}>
            <Skeleton width={160} height={18} style={{ marginBottom: 20 }} />
            {[1, 2, 3].map(i => <Skeleton key={i} width="100%" height={40} style={{ marginBottom: 8 }} />)}
          </div>
        </>
      ) : (
        <>
          {/* Summary Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
            {/* Balance */}
            <div className="card" style={{ padding: 20, position: 'relative', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, background: 'var(--accent)' }} />
              <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
                <Icon name="wallet" size={12} style={{ display: 'inline', verticalAlign: -1, marginLeft: 4 }} />
                موجودی فعلی
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtToman(data?.current_balance ?? 0)}</div>
              <Link href="/wallet" style={{ fontSize: 11, color: 'var(--accent)', marginTop: 8, display: 'inline-block' }}>شارژ کیف پول ←</Link>
            </div>

            {/* Spent this month */}
            <div className="card" style={{ padding: 20 }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
                <Icon name="payment" size={12} style={{ display: 'inline', verticalAlign: -1, marginLeft: 4 }} />
                مصرف این ماه
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtToman(data?.total_spent_this_month ?? 0)}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>{fmtIRR(data?.event_count_this_month ?? 0)} درخواست</div>
            </div>

            {/* Total tokens */}
            <div className="card" style={{ padding: 20 }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
                <Icon name="sparkles" size={12} style={{ display: 'inline', verticalAlign: -1, marginLeft: 4 }} />
                کل توکنهای مصرفی
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtTokens(totalTokens)}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
                ورودی: {fmtTokens(data?.total_input_tokens_this_month ?? 0)} | خروجی: {fmtTokens(data?.total_output_tokens_this_month ?? 0)}
              </div>
            </div>

            {/* Models used */}
            <div className="card" style={{ padding: 20 }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
                <Icon name="settings" size={12} style={{ display: 'inline', verticalAlign: -1, marginLeft: 4 }} />
                مدلهای استفاده شده
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{data?.per_model_breakdown.length ?? 0}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>مدل فعال این ماه</div>
            </div>
          </div>

          {/* Per-model breakdown */}
          {(data?.per_model_breakdown.length ?? 0) > 0 && (
            <div className="card" style={{ marginBottom: 24, overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Icon name="chart" size={16} style={{ color: 'var(--accent)' }} />
                <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>مصرف به تفکیک مدل</h2>
              </div>

              {/* Chart bars */}
              <div style={{ padding: '20px 20px 8px' }}>
                {data!.per_model_breakdown.map((m, idx) => {
                  const pct = (m.cost / maxModelCost) * 100
                  const color = modelColors[idx % modelColors.length]
                  const name = modelDisplayNames[m.model] || m.model
                  return (
                    <div key={m.model} style={{ marginBottom: 16 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ width: 8, height: 8, borderRadius: 'var(--radius-full)', background: color, flexShrink: 0 }} />
                          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{name}</span>
                          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>({m.calls} درخواست)</span>
                        </div>
                        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtToman(m.cost)}</span>
                      </div>
                      <div style={{ height: 8, borderRadius: 4, background: 'var(--border)', overflow: 'hidden' }}>
                        <div style={{ width: `${pct}%`, height: '100%', borderRadius: 4, background: color, transition: 'width 0.5s ease' }} />
                      </div>
                      <div style={{ display: 'flex', gap: 16, marginTop: 4, fontSize: 11, color: 'var(--text-muted)' }}>
                        <span>ورودی: {fmtTokens(m.input_tokens)}</span>
                        <span>خروجی: {fmtTokens(m.output_tokens)}</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Recent events table */}
          <div className="card" style={{ overflow: 'hidden' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Icon name="chart" size={16} style={{ color: 'var(--accent)' }} />
              <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>تاریخچه مصرف</h2>
            </div>

            {(data?.recent_events.length ?? 0) === 0 ? (
              <div style={{ padding: 48, textAlign: 'center' }}>
                <Icon name="info" size={32} style={{ color: 'var(--text-muted)', marginBottom: 12 }} />
                <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>هنوز مصرفی ثبت نشده است</p>
                <Link href="/chat" className="btn btn-sm btn-primary" style={{ marginTop: 16, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <Icon name="chat" size={14} />
                  شروع چت
                </Link>
              </div>
            ) : (
              <>
                {/* Table header */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px 80px 90px 100px', gap: 8, padding: '10px 20px', borderBottom: '1px solid var(--border)', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>
                  <div>مدل</div>
                  <div style={{ textAlign: 'left' }}>ورودی</div>
                  <div style={{ textAlign: 'left' }}>خروجی</div>
                  <div style={{ textAlign: 'left' }}>هزینه</div>
                  <div style={{ textAlign: 'left' }}>تاریخ</div>
                </div>
                {/* Table rows */}
                {data!.recent_events.map((evt, idx) => (
                  <div
                    key={evt.id}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 80px 80px 90px 100px',
                      gap: 8,
                      padding: '10px 20px',
                      borderBottom: idx < data!.recent_events.length - 1 ? '1px solid var(--border)' : 'none',
                      fontSize: 13,
                      alignItems: 'center',
                    }}
                  >
                    <div style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{modelDisplayNames[evt.model] || evt.model}</div>
                    <div style={{ textAlign: 'left', color: 'var(--text-secondary)', fontFeatureSettings: '"tnum"' }}>{fmtTokens(evt.input_tokens)}</div>
                    <div style={{ textAlign: 'left', color: 'var(--text-secondary)', fontFeatureSettings: '"tnum"' }}>{fmtTokens(evt.output_tokens)}</div>
                    <div style={{ textAlign: 'left', fontWeight: 600, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtIRR(evt.cost)}</div>
                    <div style={{ textAlign: 'left', fontSize: 11, color: 'var(--text-muted)' }}>{fmtDate(evt.created_at)}</div>
                  </div>
                ))}
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}
