'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  ResponsiveContainer,
  LineChart, Line, BarChart, Bar, AreaChart, Area,
  CartesianGrid, XAxis, YAxis, Tooltip, Legend,
} from 'recharts'

/* ═══════════════════════════════════════════════════════════════════════════
   Admin Dashboard Charts — RTL-aware, dark theme, Recharts
   ═══════════════════════════════════════════════════════════════════════════ */

// ─── Types ───────────────────────────────────────────────────────────────────

interface TimeseriesData {
  daily_revenue: { day: string; amount: number }[]
  daily_users: { day: string; active_users: number; new_users: number }[]
  daily_tokens: { day: string; input_tokens: number; output_tokens: number }[]
  revenue_by_model: { model: string; revenue: number; users: number; calls: number }[]
  top_users: { user_id: number; email: string; total_cost: number; total_tokens: number; calls: number }[]
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function faDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat('fa-IR', { month: 'short', day: 'numeric' }).format(new Date(iso))
  } catch { return iso }
}

function faDateShort(iso: string): string {
  try {
    const d = new Date(iso)
    return new Intl.DateTimeFormat('fa-IR', { day: 'numeric' }).format(d)
  } catch { return iso }
}

function faNum(n: number): string {
  return n.toLocaleString('fa-IR')
}

function faCompact(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toLocaleString('fa-IR', { maximumFractionDigits: 1 })} میلیارد`
  if (n >= 1_000_000) return `${(n / 1_000_000).toLocaleString('fa-IR', { maximumFractionDigits: 1 })} میلیون`
  if (n >= 1_000) return `${(n / 1_000).toLocaleString('fa-IR', { maximumFractionDigits: 1 })} هزار`
  return faNum(n)
}

// ─── Chart Wrapper Card ──────────────────────────────────────────────────────

function ChartCard({
  title, subtitle, loading, error, isEmpty, emptyIcon, emptyText, emptyHint, children, onRetry,
}: {
  title: string
  subtitle?: string
  loading: boolean
  error: string | null
  isEmpty: boolean
  emptyIcon: string
  emptyText: string
  emptyHint?: string
  children: React.ReactNode
  onRetry?: () => void
}) {
  return (
    <div className="admin-card" style={{ minHeight: 340 }}>
      <div className="mb-3">
        <h3 className="font-semibold text-sm" style={{ color: 'var(--text-primary)', textAlign: 'right' }}>{title}</h3>
        {subtitle && <p className="text-xs mt-1" style={{ color: 'var(--text-muted)', textAlign: 'right' }}>{subtitle}</p>}
      </div>
      <div style={{ direction: 'ltr' }}>
        {loading ? (
          <ChartSkeleton />
        ) : error ? (
          <ChartError message={error} onRetry={onRetry} />
        ) : isEmpty ? (
          <ChartEmpty icon={emptyIcon} text={emptyText} hint={emptyHint} />
        ) : (
          children
        )}
      </div>
    </div>
  )
}

// ─── Skeleton (pulsing bars) ─────────────────────────────────────────────────

function ChartSkeleton() {
  const bars = Array.from({ length: 12 }, () => 20 + Math.random() * 60)
  return (
    <div className="animate-pulse" style={{ padding: '16px 0' }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 200, justifyContent: 'center' }}>
        {bars.map((h, i) => (
          <div key={i} style={{
            width: '100%', maxWidth: 32, height: `${h}%`,
            borderRadius: 4, background: 'var(--bg-elevated, #1e1e2e)',
          }} />
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, padding: '0 8px' }}>
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="animate-pulse" style={{
            width: 28, height: 10, borderRadius: 3,
            background: 'var(--bg-elevated, #1e1e2e)',
          }} />
        ))}
      </div>
    </div>
  )
}

// ─── Error State ─────────────────────────────────────────────────────────────

function ChartError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 220, gap: 12 }}>
      <div style={{
        width: 48, height: 48, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'var(--danger, #ef4444)', opacity: 0.15,
      }}>
        <span style={{ fontSize: 22, opacity: 1 }}>⚠️</span>
      </div>
      <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>خطا در بارگذاری نمودار</p>
      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{message || 'امکان دریافت داده از سرور وجود ندارد'}</p>
      {onRetry && (
        <button onClick={onRetry} className="btn btn-sm" style={{ marginTop: 4 }}>
          🔄 تلاش مجدد
        </button>
      )}
    </div>
  )
}

// ─── Empty State ─────────────────────────────────────────────────────────────

function ChartEmpty({ icon, text, hint }: { icon: string; text: string; hint?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 220, gap: 8 }}>
      <span style={{ fontSize: 36, opacity: 0.6 }}>{icon}</span>
      <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{text}</p>
      {hint && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{hint}</p>}
    </div>
  )
}

// ─── Shared chart style ──────────────────────────────────────────────────────

const GRID_STYLE = { strokeDasharray: '3 3', stroke: 'var(--border, #2a2a3a)' }
const TICK_STYLE = { fontSize: 11, fill: 'var(--text-secondary, #9ca3af)' }
const TOOLTIP_STYLE = {
  contentStyle: {
    background: 'var(--bg-elevated, #1e1e2e)',
    border: '1px solid var(--border, #2a2a3a)',
    borderRadius: 8,
    direction: 'rtl' as const,
    fontSize: 12,
  },
  labelStyle: { color: 'var(--text-primary, #e5e7eb)' },
  itemStyle: { color: 'var(--text-secondary, #9ca3af)' },
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function AdminCharts() {
  const [data, setData] = useState<TimeseriesData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const token = localStorage.getItem('admin_token') || ''
      const res = await fetch('/api/admin/analytics/timeseries', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error(`${res.status}`)
      const json = await res.json()
      setData(json)
    } catch (e: any) {
      setError(e?.message || 'خطای شبکه')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  // Transform data for recharts
  const revenueData = (data?.daily_revenue || []).map(d => ({
    ...d,
    dateLabel: faDate(d.day),
    dateShort: faDateShort(d.day),
  }))

  const usersData = (data?.daily_users || []).map(d => ({
    ...d,
    dateLabel: faDate(d.day),
    dateShort: faDateShort(d.day),
  }))

  const tokensData = (data?.daily_tokens || []).map(d => ({
    ...d,
    dateLabel: faDate(d.day),
    dateShort: faDateShort(d.day),
  }))

  const modelData = (data?.revenue_by_model || []).map(d => ({
    ...d,
    shortModel: d.model.length > 20 ? d.model.slice(0, 20) + '…' : d.model,
  }))

  const hasRevenue = revenueData.some(d => d.amount > 0)
  const hasUsers = usersData.some(d => d.active_users > 0 || d.new_users > 0)
  const hasTokens = tokensData.some(d => d.input_tokens > 0 || d.output_tokens > 0)
  const hasModels = modelData.length > 0

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" style={{ direction: 'rtl' }}>
      {/* 1) Revenue Line */}
      <ChartCard
        title="درآمد روزانه"
        subtitle="۳۰ روز اخیر (ریال)"
        loading={loading}
        error={error}
        isEmpty={!hasRevenue}
        emptyIcon="💰"
        emptyText="هنوز درآمدی ثبت نشده"
        emptyHint="با اولین استفاده کاربران، نمودار درآمد نمایان می‌شود"
        onRetry={fetchData}
      >
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={revenueData}>
            <CartesianGrid {...GRID_STYLE} />
            <XAxis dataKey="dateShort" tick={TICK_STYLE} />
            <YAxis tick={TICK_STYLE} tickFormatter={faCompact} />
            <Tooltip
              {...TOOLTIP_STYLE}
              formatter={(v: any) => [`${faNum(v)} ریال`, 'درآمد']}
              labelFormatter={(l: any) => `تاریخ: ${l}`}
            />
            <Line
              type="monotone" dataKey="amount" name="درآمد"
              stroke="var(--ok, #22c55e)" strokeWidth={2}
              dot={false} activeDot={{ r: 4 }}
              fill="url(#revenueGrad)" fillOpacity={0.1}
            />
            <defs>
              <linearGradient id="revenueGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--ok, #22c55e)" stopOpacity={0.3} />
                <stop offset="100%" stopColor="var(--ok, #22c55e)" stopOpacity={0} />
              </linearGradient>
            </defs>
          </LineChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* 2) Users Bar */}
      <ChartCard
        title="کاربران فعال و جدید"
        subtitle="۳۰ روز اخیر"
        loading={loading}
        error={error}
        isEmpty={!hasUsers}
        emptyIcon="👥"
        emptyText="کاربر فعالی در این بازه وجود ندارد"
        onRetry={fetchData}
      >
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={usersData}>
            <CartesianGrid {...GRID_STYLE} />
            <XAxis dataKey="dateShort" tick={TICK_STYLE} />
            <YAxis tick={TICK_STYLE} />
            <Tooltip
              {...TOOLTIP_STYLE}
              formatter={(v: any, name: any) => [faNum(v), name === 'active_users' ? 'فعال' : 'جدید']}
              labelFormatter={(l: any) => `تاریخ: ${l}`}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} formatter={() => ''} />
            <Bar dataKey="active_users" name="فعال" fill="var(--accent, #6366f1)" radius={[3, 3, 0, 0]} />
            <Bar dataKey="new_users" name="جدید" fill="var(--accent, #6366f1)" opacity={0.4} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* 3) Tokens Stacked Area */}
      <ChartCard
        title="حجم توکن ورودی/خروجی"
        subtitle="۳۰ روز اخیر"
        loading={loading}
        error={error}
        isEmpty={!hasTokens}
        emptyIcon="📊"
        emptyText="مصرف توکن در این بازه ثبت نشده"
        onRetry={fetchData}
      >
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={tokensData}>
            <CartesianGrid {...GRID_STYLE} />
            <XAxis dataKey="dateShort" tick={TICK_STYLE} />
            <YAxis tick={TICK_STYLE} tickFormatter={faCompact} />
            <Tooltip
              {...TOOLTIP_STYLE}
              formatter={(v: any, name: any) => [faNum(v), name === 'input_tokens' ? 'ورودی' : 'خروجی']}
              labelFormatter={(l: any) => `تاریخ: ${l}`}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Area
              type="monotone" dataKey="input_tokens" name="ورودی"
              stackId="1" stroke="var(--accent-light, #818cf8)"
              fill="var(--accent-light, #818cf8)" fillOpacity={0.3}
            />
            <Area
              type="monotone" dataKey="output_tokens" name="خروجی"
              stackId="1" stroke="var(--accent, #6366f1)"
              fill="var(--accent, #6366f1)" fillOpacity={0.3}
            />
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* 4) Revenue by Model Horizontal Bar */}
      <ChartCard
        title="درآمد بر اساس مدل"
        subtitle="ماه جاری"
        loading={loading}
        error={error}
        isEmpty={!hasModels}
        emptyIcon="🤖"
        emptyText="داده‌ای برای نمایش موجود نیست"
        onRetry={fetchData}
      >
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={modelData} layout="vertical">
            <CartesianGrid {...GRID_STYLE} />
            <XAxis type="number" tick={TICK_STYLE} tickFormatter={faCompact} />
            <YAxis type="category" dataKey="shortModel" tick={TICK_STYLE} width={100} />
            <Tooltip
              {...TOOLTIP_STYLE}
              formatter={(v: any, _name: any, p: any) => [
                `${faNum(v)} ریال | ${faNum(p?.payload?.users || 0)} کاربر | ${faNum(p?.payload?.calls || 0)} درخواست`,
                'درآمد',
              ]}
              labelFormatter={(l: any) => `مدل: ${l}`}
            />
            <Bar dataKey="revenue" name="درآمد" fill="var(--ok, #22c55e)" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  )
}
