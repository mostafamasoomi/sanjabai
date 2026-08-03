'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { faNum, faPrice, faCompact, faPercent, toFaDigits } from '@/lib/format'

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

type RangeKey = 'week' | 'month' | 'all'

/* ═══════════════════════════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════════════════════════ */

const fmtToman = (n: number) => faPrice(n)
const fmtIRR = (n: number) => faNum(n)
// Was `1.2M` / `34.0K` — Latin abbreviations that the RTL paragraph reorders
// away from their number. faCompact gives the Persian equivalent instead.
const fmtTokens = (n: number) => faCompact(n)
const fmtDate = (s: string | null) => {
  if (!s) return '—'
  return toFaDigits(new Date(s).toLocaleDateString('fa-IR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }))
}
const fmtDateShort = (s: string | null) => {
  if (!s) return '—'
  return toFaDigits(new Date(s).toLocaleDateString('fa-IR', { month: 'short', day: 'numeric' }))
}
// `٪` rather than `%`: the Latin sign is an LTR run that gets pushed away
// from its number in an RTL paragraph.
const fmtPct = (n: number) => faPercent(n * 100, 1)

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

const modelColor = (i: number) => modelColors[i % modelColors.length]
const modelName = (m: string) => modelDisplayNames[m] || m

/* ═══════════════════════════════════════════════════════════════════════════
   Skeleton
   ═══════════════════════════════════════════════════════════════════════════ */

function Skeleton({ width, height, style }: { width?: number | string; height?: number; style?: React.CSSProperties }) {
  return <div className="skeleton" style={{ width, height, borderRadius: 'var(--radius-sm)', ...style }} />
}

/* ═══════════════════════════════════════════════════════════════════════════
   Donut chart (pure SVG, no library)
   ═══════════════════════════════════════════════════════════════════════════ */

function DonutChart({
  data,
  size = 200,
  thickness = 26,
  centerLabel,
  centerValue,
}: {
  data: { label: string; value: number; color: string }[]
  size?: number
  thickness?: number
  centerLabel?: string
  centerValue?: string
}) {
  const radius = (size - thickness) / 2
  const circumference = 2 * Math.PI * radius
  const total = data.reduce((s, d) => s + d.value, 0) || 1
  let offset = 0
  return (
    <div style={{ position: 'relative', width: size, height: size, margin: '0 auto' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }} aria-hidden>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--border)"
          strokeWidth={thickness}
        />
        {data.map((d, i) => {
          const frac = d.value / total
          const len = frac * circumference
          const seg = (
            <circle
              key={i}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={d.color}
              strokeWidth={thickness}
              strokeDasharray={`${len} ${circumference - len}`}
              strokeDashoffset={-offset}
              strokeLinecap="butt"
              style={{ transition: 'stroke-dasharray 0.6s ease, stroke-dashoffset 0.6s ease' }}
            />
          )
          offset += len
          return seg
        })}
      </svg>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 2,
        }}
      >
        {centerValue && (
          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>
            {centerValue}
          </div>
        )}
        {centerLabel && (
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{centerLabel}</div>
        )}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Card wrapper with fade-in animation
   ═══════════════════════════════════════════════════════════════════════════ */

function FadeInCard({
  children,
  style,
  delay = 0,
  className,
}: {
  children: React.ReactNode
  style?: React.CSSProperties
  delay?: number
  className?: string
}) {
  return (
    <div
      className={`fade-in ${className || ''}`}
      style={{ animationDelay: `${delay}ms`, ...style }}
    >
      {children}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Main Page
   ═══════════════════════════════════════════════════════════════════════════ */

export default function UsagePage() {
  const { token, user, loading: authLoading } = useAuth()
  const [data, setData] = useState<UsageData | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [range, setRange] = useState<RangeKey>('month')
  const [hoveredLegend, setHoveredLegend] = useState<number | null>(null)

  const fetchUsage = useCallback(async (silent = false) => {
    if (!token) return
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      const res = await fetch('/api/me/usage', { headers: { Authorization: `Bearer ${token}` } })
      if (res.ok) {
        const d = await res.json()
        // Normalise the collections up front. Every derived value below is a
        // useMemo that maps/filters/reduces over them, so one missing key in
        // the response — an older backend, a user with no history — threw
        // during render and the error boundary replaced the whole page with
        // "خطای سیستمی". Defaulting here keeps that a legitimate empty state.
        setData({
          ...d,
          recent_events: Array.isArray(d?.recent_events) ? d.recent_events : [],
          per_model_breakdown: Array.isArray(d?.per_model_breakdown) ? d.per_model_breakdown : [],
        })
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

  /* ── Derived: filter events by selected range ── */
  const rangedEvents = useMemo(() => {
    if (!data) return []
    const now = Date.now()
    const dayMs = 86_400_000
    const weekStart = now - 7 * dayMs
    const monthStart = now - 30 * dayMs
    return data.recent_events.filter((e) => {
      if (range === 'all') return true
      const t = e.created_at ? new Date(e.created_at).getTime() : 0
      if (range === 'week') return t >= weekStart
      if (range === 'month') return t >= monthStart
      return true
    })
  }, [data, range])

  /* ── Derived: most expensive call ── */
  const mostExpensive = useMemo(() => {
    if (!data || data.recent_events.length === 0) return null
    return data.recent_events.reduce((m, e) => (e.cost > m.cost ? e : m), data.recent_events[0])
  }, [data])

  /* ── Derived: per-model token efficiency + cost share ── */
  const modelStats = useMemo(() => {
    if (!data) return []
    return data.per_model_breakdown.map((m, i) => {
      const totalTokens = m.input_tokens + m.output_tokens
      const avgTokensPerCall = m.calls > 0 ? totalTokens / m.calls : 0
      const costPerCall = m.calls > 0 ? m.cost / m.calls : 0
      return {
        ...m,
        index: i,
        color: modelColor(i),
        name: modelName(m.model),
        totalTokens,
        avgTokensPerCall,
        costPerCall,
      }
    })
  }, [data])

  const totalModelCost = useMemo(
    () => modelStats.reduce((s, m) => s + m.cost, 0) || 1,
    [modelStats],
  )

  const donutData = useMemo(
    () => modelStats.map((m) => ({ label: m.name, value: m.cost, color: m.color })),
    [modelStats],
  )

  /* ── Derived: 30-day daily sparkline (cost) ── */
  const sparkline = useMemo(() => {
    const days = 30
    const now = Date.now()
    const dayMs = 86_400_000
    const buckets: { date: Date; cost: number; calls: number }[] = []
    const index = new Map<string, number>()
    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(now - i * dayMs)
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
      index.set(key, buckets.length)
      buckets.push({ date: d, cost: 0, calls: 0 })
    }
    if (data) {
      for (const e of data.recent_events) {
        if (!e.created_at) continue
        const d = new Date(e.created_at)
        const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
        const idx = index.get(key)
        if (idx !== undefined) {
          buckets[idx].cost += e.cost
          buckets[idx].calls += 1
        }
      }
    }
    const maxCost = Math.max(...buckets.map((b) => b.cost), 0.0001)
    return { buckets, maxCost }
  }, [data])

  /* ── Export CSV ── */
  const exportCsv = useCallback(() => {
    if (!data) return
    const headers = ['id', 'model', 'input_tokens', 'output_tokens', 'cost', 'created_at']
    const rows = rangedEvents.map((e) => [
      e.id,
      e.model,
      e.input_tokens,
      e.output_tokens,
      e.cost,
      e.created_at || '',
    ])
    const csv =
      '﻿' + // BOM for Excel Persian support
      [headers.join(','), ...rows.map((r) => r.join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `usage-${range}-${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    toast('فایل CSV دانلود شد', 'success')
  }, [data, rangedEvents, range])

  if (authLoading) return null

  if (!user) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <div className="card" style={{ textAlign: 'center', padding: '48px 32px', maxWidth: 400 }}>
          <div style={{ width: 56, height: 56, borderRadius: 'var(--radius-full)', background: 'var(--accent-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px' }}>
            <Icon name="chart" size={28} className="text-accent" />
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
  const hasAnyData = (data?.per_model_breakdown.length ?? 0) > 0 || (data?.recent_events.length ?? 0) > 0

  const rangeLabels: Record<RangeKey, string> = {
    week: 'این هفته',
    month: 'این ماه',
    all: 'همه زمان‌ها',
  }

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '32px 20px 64px' }} className="usage-page">
      {/* Header */}
      <div className="usage-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24, gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 'var(--radius-full)', background: 'var(--accent-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Icon name="chart" size={18} className="text-accent" />
          </div>
          <div>
            <h1 className="page-title">گزارش مصرف</h1>
            <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>تحلیل هزینه، توکن و عملکرد مدل‌ها</p>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            className="btn btn-sm btn-secondary"
            onClick={exportCsv}
            disabled={!hasAnyData}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            aria-label="خروجی CSV"
          >
            <Icon name="external" size={14} />
            خروجی CSV
          </button>
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
      </div>

      {/* Controls: date range */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        <Icon name="calendar" size={16} className="text-muted" />
        <div style={{ display: 'inline-flex', background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-full)', padding: 4 }}>
          {(['week', 'month', 'all'] as RangeKey[]).map((k) => (
            <button
              key={k}
              onClick={() => setRange(k)}
              className="range-pill"
              style={{
                border: 'none',
                cursor: 'pointer',
                padding: '6px 16px',
                borderRadius: 'var(--radius-full)',
                fontSize: 13,
                fontWeight: 600,
                background: range === k ? 'var(--accent)' : 'transparent',
                color: range === k ? 'var(--text-on-accent)' : 'var(--text-secondary)',
                transition: 'background 0.2s ease, color 0.2s ease',
                fontFamily: 'var(--font-sans)',
              }}
            >
              {rangeLabels[k]}
            </button>
          ))}
        </div>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {faNum(rangedEvents.length)} رویداد در بازه انتخابی
        </span>
      </div>

      {loading ? (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 16 }}>
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="card" style={{ padding: 20 }}>
                <Skeleton width={100} height={12} style={{ marginBottom: 12 }} />
                <Skeleton width={140} height={28} style={{ marginBottom: 8 }} />
                <Skeleton width={80} height={10} />
              </div>
            ))}
          </div>
          <div className="card" style={{ marginBottom: 16 }}>
            <Skeleton width={160} height={18} style={{ margin: 20 }} />
            <Skeleton width="100%" height={200} style={{ margin: '0 20px 20px' }} />
          </div>
        </>
      ) : !hasAnyData ? (
        /* Empty state */
        <FadeInCard className="card" style={{ padding: '56px 24px', textAlign: 'center' }}>
          <div style={{ width: 96, height: 96, margin: '0 auto 24px', position: 'relative' }}>
            <div style={{ position: 'absolute', inset: 0, borderRadius: 'var(--radius-full)', background: 'var(--accent-dim)' }} />
            <div style={{ position: 'absolute', inset: 22, borderRadius: 'var(--radius-full)', background: 'var(--bg-surface)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width={40} height={40} viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth={1.5} aria-hidden>
                <path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z" fill="var(--accent-dim)" stroke="var(--accent)" strokeLinejoin="round" />
              </svg>
            </div>
          </div>
          <h2 className="card-title" style={{ marginBottom: 8 }}>هنوز مصرفی ثبت نشده است</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: 14, maxWidth: 360, margin: '0 auto 24px' }}>
            با ارسال اولین پیام در چت، گزارش‌های دقیق مصرف توکن و هزینه اینجا نمایش داده می‌شود.
          </p>
          <Link href="/chat" className="btn btn-lg btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <Icon name="chat" size={16} />
            شروع چت
          </Link>
        </FadeInCard>
      ) : (
        <>
          {/* Summary Cards */}
          <div className="usage-cards" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 16 }}>
            {/* Balance */}
            <FadeInCard className="card" delay={0} style={{ padding: 20, position: 'relative', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', top: 0, insetInlineStart: 0, insetInlineEnd: 0, height: 3, background: 'var(--accent)' }} />
              <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
                <Icon name="wallet" size={12} style={{ display: 'inline', verticalAlign: -1, marginInlineStart: 4 }} />
                موجودی فعلی
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtToman(data?.current_balance ?? 0)}</div>
              <Link href="/wallet" style={{ fontSize: 11, color: 'var(--accent)', marginTop: 8, display: 'inline-block' }}>شارژ کیف پول ←</Link>
            </FadeInCard>

            {/* Spent this month */}
            <FadeInCard className="card" delay={60} style={{ padding: 20 }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
                <Icon name="payment" size={12} style={{ display: 'inline', verticalAlign: -1, marginInlineStart: 4 }} />
                مصرف {rangeLabels[range]}
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtToman(rangedEvents.reduce((s, e) => s + e.cost, 0))}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>{fmtIRR(rangedEvents.length)} درخواست</div>
            </FadeInCard>

            {/* Total tokens */}
            <FadeInCard className="card" delay={120} style={{ padding: 20 }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
                <Icon name="sparkles" size={12} style={{ display: 'inline', verticalAlign: -1, marginInlineStart: 4 }} />
                کل توکن‌های مصرفی
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtTokens(rangedEvents.reduce((s, e) => s + e.input_tokens + e.output_tokens, 0))}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
                ورودی: {fmtTokens(rangedEvents.reduce((s, e) => s + e.input_tokens, 0))} | خروجی: {fmtTokens(rangedEvents.reduce((s, e) => s + e.output_tokens, 0))}
              </div>
            </FadeInCard>

            {/* Models used */}
            <FadeInCard className="card" delay={180} style={{ padding: 20 }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
                <Icon name="models" size={12} style={{ display: 'inline', verticalAlign: -1, marginInlineStart: 4 }} />
                مدل‌های استفاده شده
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{new Set(rangedEvents.map((e) => e.model)).size}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>مدل فعال بازه انتخابی</div>
            </FadeInCard>
          </div>

          {/* Most expensive call highlight */}
          {mostExpensive && (
            <FadeInCard className="card" delay={220} style={{ marginBottom: 16, padding: 20, background: 'linear-gradient(135deg, var(--accent-dim), transparent)', border: '1px solid var(--border-strong)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
                <div style={{ width: 44, height: 44, borderRadius: 'var(--radius-md)', background: 'var(--accent-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Icon name="warning" size={22} style={{ color: 'var(--warning)' }} />
                </div>
                <div style={{ flex: 1, minWidth: 160 }}>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 2 }}>گران‌ترین درخواست</div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{modelName(mostExpensive.model)}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{fmtDate(mostExpensive.created_at)}</div>
                </div>
                <div style={{ textAlign: 'left' }}>
                  <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtIRR(mostExpensive.cost)}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFeatureSettings: '"tnum"' }}>
                    {fmtTokens(mostExpensive.input_tokens)} ورودی / {fmtTokens(mostExpensive.output_tokens)} خروجی
                  </div>
                </div>
              </div>
            </FadeInCard>
          )}

          {/* Charts row: donut + sparkline */}
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1.2fr)', gap: 16, marginBottom: 16 }} className="usage-charts">
            {/* Donut: model cost distribution */}
            <FadeInCard className="card" delay={260} style={{ padding: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <Icon name="chart" size={16} className="text-accent" />
                <h2 className="card-title">توزیع هزینه مدل‌ها</h2>
              </div>
              {modelStats.length > 0 ? (
                <>
                  <DonutChart
                    data={donutData}
                    centerValue={fmtIRR(totalModelCost)}
                    centerLabel="تومان"
                  />
                  <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {modelStats.map((m, i) => (
                      <div
                        key={m.model}
                        onMouseEnter={() => setHoveredLegend(i)}
                        onMouseLeave={() => setHoveredLegend(null)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          fontSize: 12,
                          padding: '4px 6px',
                          borderRadius: 'var(--radius-sm)',
                          background: hoveredLegend === i ? 'var(--bg-hover)' : 'transparent',
                          transition: 'background 0.15s ease',
                        }}
                      >
                        <div style={{ width: 10, height: 10, borderRadius: 'var(--radius-full)', background: m.color, flexShrink: 0 }} />
                        <span style={{ flex: 1, color: 'var(--text-secondary)', fontWeight: 600 }}>{m.name}</span>
                        <span style={{ color: 'var(--text-muted)', fontFeatureSettings: '"tnum"' }}>{fmtPct(m.cost / totalModelCost)}</span>
                        <span style={{ color: 'var(--text-primary)', fontWeight: 700, fontFeatureSettings: '"tnum"', minWidth: 72, textAlign: 'left' }}>{fmtIRR(m.cost)}</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>داده‌ای برای نمایش نمودار وجود ندارد</div>
              )}
            </FadeInCard>

            {/* Sparkline: daily usage (last 30 days) */}
            <FadeInCard className="card" delay={320} style={{ padding: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Icon name="calendar" size={16} className="text-accent" />
                  <h2 className="card-title">مصرف روزانه</h2>
                </div>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>۳۰ روز گذشته</span>
              </div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'flex-end',
                  gap: 2,
                  height: 160,
                  paddingTop: 8,
                }}
                aria-label="نمودار مصرف روزانه ۳۰ روز گذشته"
              >
                {sparkline.buckets.map((b, i) => {
                  const h = Math.max((b.cost / sparkline.maxCost) * 100, b.cost > 0 ? 4 : 1.5)
                  return (
                    <div
                      key={i}
                      title={`${fmtDateShort(b.date.toISOString())}: ${fmtIRR(b.cost)} تومان · ${b.calls} درخواست`}
                      style={{
                        flex: 1,
                        height: `${h}%`,
                        minWidth: 2,
                        borderRadius: '3px 3px 0 0',
                        background: b.cost > 0 ? 'var(--accent)' : 'var(--border)',
                        opacity: b.cost > 0 ? 0.85 : 0.4,
                        transition: 'height 0.5s ease, background 0.2s ease, opacity 0.2s ease',
                        alignSelf: 'flex-end',
                      }}
                    />
                  )
                })}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontSize: 10, color: 'var(--text-muted)' }}>
                <span>{fmtDateShort(sparkline.buckets[0]?.date.toISOString() ?? null)}</span>
                <span>{fmtDateShort(sparkline.buckets[sparkline.buckets.length - 1]?.date.toISOString() ?? null)}</span>
              </div>
            </FadeInCard>
          </div>

          {/* Per-model breakdown with token efficiency */}
          {(data?.per_model_breakdown.length ?? 0) > 0 && (
            <FadeInCard className="card" delay={380} style={{ marginBottom: 16, overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Icon name="models" size={16} className="text-accent" />
                <h2 className="card-title">مصرف به تفکیک مدل</h2>
              </div>

              <div style={{ padding: '20px 20px 8px' }}>
                {modelStats.map((m, idx) => {
                  const pct = (m.cost / maxModelCost) * 100
                  return (
                    <div
                      key={m.model}
                      className="slide-up"
                      style={{ marginBottom: 18, animationDelay: `${420 + Math.min(idx, 10) * 30}ms` }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6, flexWrap: 'wrap', gap: 6 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ width: 8, height: 8, borderRadius: 'var(--radius-full)', background: m.color, flexShrink: 0 }} />
                          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{m.name}</span>
                          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>({m.calls} درخواست)</span>
                        </div>
                        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtToman(m.cost)}</span>
                      </div>
                      <div style={{ height: 8, borderRadius: 4, background: 'var(--border)', overflow: 'hidden' }}>
                        <div style={{ width: `${pct}%`, height: '100%', borderRadius: 4, background: m.color, transition: 'width 0.6s ease' }} />
                      </div>
                      <div style={{ display: 'flex', gap: 16, marginTop: 6, fontSize: 11, color: 'var(--text-muted)', flexWrap: 'wrap' }}>
                        <span>ورودی: {fmtTokens(m.input_tokens)}</span>
                        <span>خروجی: {fmtTokens(m.output_tokens)}</span>
                        <span className="text-accent">
                          <Icon name="compare" size={11} style={{ display: 'inline', verticalAlign: -1, marginInlineStart: 3 }} />
                          میانگین: {fmtTokens(Math.round(m.avgTokensPerCall))} توکن/درخواست
                        </span>
                        <span>هزینه/درخواست: {fmtIRR(Math.round(m.costPerCall))}</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </FadeInCard>
          )}

          {/* Recent events table */}
          <FadeInCard className="card overflow-hidden" delay={440}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Icon name="chart" size={16} className="text-accent" />
              <h2 className="card-title">تاریخچه مصرف</h2>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', marginInlineStart: 'auto' }}>{faNum(rangedEvents.length)} مورد</span>
            </div>

            {rangedEvents.length === 0 ? (
              <div style={{ padding: 48, textAlign: 'center' }}>
                <Icon name="info" size={32} style={{ color: 'var(--text-muted)', marginBottom: 12 }} />
                <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>رویدادی در بازه انتخابی یافت نشد</p>
              </div>
            ) : (
              <>
                {/* Table header */}
                <div className="usage-table-head" style={{ display: 'grid', gridTemplateColumns: '1fr 80px 80px 90px 110px', gap: 8, padding: '10px 20px', borderBottom: '1px solid var(--border)', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>
                  <div>مدل</div>
                  <div>ورودی</div>
                  <div>خروجی</div>
                  <div>هزینه</div>
                  <div>تاریخ</div>
                </div>
                {/* Table rows */}
                <div className="usage-table-body">
                  {rangedEvents.slice(0, 50).map((evt, idx) => (
                    <div
                      key={evt.id}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 80px 80px 90px 110px',
                        gap: 8,
                        padding: '10px 20px',
                        borderBottom: idx < rangedEvents.slice(0, 50).length - 1 ? '1px solid var(--border)' : 'none',
                        fontSize: 13,
                        alignItems: 'center',
                        transition: 'background 0.15s ease',
                        animationDelay: `${480 + Math.min(idx, 10) * 30}ms`,
                      }}
                      className="usage-row slide-up"
                    >
                      <div style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{modelName(evt.model)}</div>
                      <div style={{ color: 'var(--text-secondary)', fontFeatureSettings: '"tnum"' }}>{fmtTokens(evt.input_tokens)}</div>
                      <div style={{ color: 'var(--text-secondary)', fontFeatureSettings: '"tnum"' }}>{fmtTokens(evt.output_tokens)}</div>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtIRR(evt.cost)}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{fmtDate(evt.created_at)}</div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </FadeInCard>
        </>
      )}
    </div>
  )
}
