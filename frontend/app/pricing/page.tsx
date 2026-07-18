'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════════════════════════════════ */

type ModelPricing = {
  id: string
  providerModelId: string
  displayName: string
  description?: string
  contextWindow?: number
  pricing: {
    currency: string
    inputPerMillion: number
    outputPerMillion: number
    usd?: {
      inputPerMillion: number
      outputPerMillion: number
    }
    exchangeRate?: number
  }
  availability: string
}

/* ═══════════════════════════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════════════════════════ */

const fmtToman = (n: number) => `${n.toLocaleString('fa-IR')} تومان`
const fmtIRR = (n: number) => n.toLocaleString('fa-IR')
const fmtUSD = (n: number) => n < 1 ? `$${n.toFixed(3)}` : `$${n.toFixed(2)}`

const modelIcons: Record<string, string> = {
  'agnes': '⚡',
  'gemini': '💎',
  'mimo': '🧠',
  'mistral': '🌀',
  'tencent': '🔥',
}

function getModelIcon(modelId: string): string {
  for (const [key, icon] of Object.entries(modelIcons)) {
    if (modelId.toLowerCase().includes(key)) return icon
  }
  return '🤖'
}

function getModelTier(modelId: string): { label: string; color: string } {
  if (modelId.includes('flash') && !modelId.includes('agnes')) return { label: 'اقتصادی', color: 'var(--positive)' }
  if (modelId.includes('pro-ultraspeed')) return { label: 'سریع', color: 'var(--warning)' }
  if (modelId.includes('pro')) return { label: 'پیشرفته', color: 'var(--accent)' }
  if (modelId.includes('large') || modelId.includes('medium')) return { label: 'حرفهای', color: 'var(--accent)' }
  return { label: 'اقتصادی', color: 'var(--positive)' }
}

/* ═══════════════════════════════════════════════════════════════════════════
   Main Page
   ═══════════════════════════════════════════════════════════════════════════ */

export default function PricingPage() {
  const { token, user, loading: authLoading } = useAuth()
  const [models, setModels] = useState<ModelPricing[]>([])
  const [loading, setLoading] = useState(true)
  const [balance, setBalance] = useState<number | null>(null)
  const [sortBy, setSortBy] = useState<'name' | 'input' | 'output'>('name')
  const [exchangeRate, setExchangeRate] = useState<number | null>(null)
  const [cachedAt, setCachedAt] = useState<string | null>(null)

  const fetchModels = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/catalog/models')
      if (res.ok) {
        const data = await res.json()
        const available = (data.data || []).filter(
          (m: ModelPricing) => m.availability === 'available' && m.pricing && (m.pricing.inputPerMillion > 0 || m.pricing.outputPerMillion > 0)
        )
        setModels(available)
        if (data.exchangeRate) setExchangeRate(data.exchangeRate)
      }
    } catch {
      toast('خطا در دریافت اطلاعات مدلها', 'error')
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchExchangeRate = useCallback(async () => {
    try {
      const res = await fetch('/api/exchange-rate')
      if (res.ok) {
        const data = await res.json()
        setExchangeRate(data.usd_to_irt || null)
        setCachedAt(data.cached_at || null)
      }
    } catch { /* silent */ }
  }, [])

  const fetchBalance = useCallback(async () => {
    if (!token) return
    try {
      const res = await fetch('/api/wallet', { headers: { Authorization: `Bearer ${token}` } })
      if (res.ok) {
        const data = await res.json()
        setBalance(data.balance ?? 0)
      }
    } catch { /* silent */ }
  }, [token])

  useEffect(() => { fetchModels(); fetchExchangeRate() }, [fetchModels, fetchExchangeRate])
  useEffect(() => { if (!authLoading && token) fetchBalance() }, [authLoading, token, fetchBalance])

  const sortedModels = [...models].sort((a, b) => {
    if (sortBy === 'input') return a.pricing.inputPerMillion - b.pricing.inputPerMillion
    if (sortBy === 'output') return a.pricing.outputPerMillion - b.pricing.outputPerMillion
    return a.displayName.localeCompare(b.displayName)
  })

  const maxInput = Math.max(...models.map(m => m.pricing.inputPerMillion), 1)
  const maxOutput = Math.max(...models.map(m => m.pricing.outputPerMillion), 1)

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '32px 20px 64px' }}>

      {/* Hero */}
      <div style={{ textAlign: 'center', marginBottom: 48 }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 16px', borderRadius: 'var(--radius-full)', background: 'var(--accent-dim)', marginBottom: 20 }}>
          <Icon name="sparkles" size={16} className="text-accent" />
          <span className="text-[13px] text-accent font-semibold">تعرفه مدلها</span>
        </div>
        <h1 style={{ fontSize: 32, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 12, lineHeight: 1.4 }}>
          قیمت‌گذاری شفاف، پرداخت به ازای مصرف
        </h1>
        <p style={{ fontSize: 15, color: 'var(--text-secondary)', maxWidth: 560, margin: '0 auto', lineHeight: 1.7 }}>
          هر مدل هوش مصنوعی قیمت مشخصی دارد. فقط به اندازه مصرف واقعی خود پرداخت کنید. قیمتها به تومان به ازای هر ۱ میلیون توکن هستند.
        </p>
      </div>

      {/* Exchange Rate Banner */}
      {exchangeRate && (
        <div className="card" style={{ padding: '14px 20px', marginBottom: 24, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, background: 'linear-gradient(135deg, rgba(124,111,247,0.06) 0%, rgba(103,232,249,0.03) 100%)' }}>
          <div className="flex items-center gap-2.5">
            <Icon name="refresh" size={18} className="text-accent" />
            <span className="text-sm text-secondary">نرخ ارز:</span>
            <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>
              ۱ دلار = {exchangeRate.toLocaleString('fa-IR')} تومان
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-muted)', background: 'var(--bg-hover)', padding: '2px 8px', borderRadius: 'var(--radius-full)' }}>
            </span>
          </div>
          {cachedAt && (
            <span style={{ fontSize: 11, color: 'var(--text-muted)', direction: 'ltr' }}>
              بروزرسانی: {new Date(cachedAt).toLocaleTimeString('fa-IR')}
            </span>
          )}
        </div>
      )}

      {/* Balance card (if logged in) */}
      {user && balance !== null && (
        <div className="card" style={{ padding: '16px 20px', marginBottom: 24, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div className="flex items-center gap-2.5">
            <Icon name="wallet" size={18} className="text-accent" />
            <span className="text-sm text-secondary">موجودی کیف پول:</span>
            <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>{fmtToman(balance)}</span>
          </div>
          <Link href="/wallet" className="btn btn-sm btn-primary" className="inline-flex items-center gap-1.5">
            <Icon name="plus" size={14} />
            شارژ کیف پول
          </Link>
        </div>
      )}

      {/* Pricing Table */}
      <div className="card" className="overflow-hidden mb-8">
        {/* Table Header */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 130px 130px 130px 130px 90px', gap: 8, padding: '14px 16px', borderBottom: '2px solid var(--border)', background: 'var(--bg-hover)', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>
          <div role="button" tabIndex={0} className="cursor-pointer" onClick={() => setSortBy('name')}>مدل {sortBy === 'name' && '↕'}</div>
          <div role="button" tabIndex={0} className="text-start cursor-pointer" onClick={() => setSortBy('input')}>ورودی/1M (USD) {sortBy === 'input' && '↕'}</div>
          <div role="button" tabIndex={0} className="text-start cursor-pointer" onClick={() => setSortBy('input')}>ورودی/1M (تومان) {sortBy === 'input' && '↕'}</div>
          <div role="button" tabIndex={0} className="text-start cursor-pointer" onClick={() => setSortBy('output')}>خروجی/1M (USD) {sortBy === 'output' && '↕'}</div>
          <div role="button" tabIndex={0} className="text-start cursor-pointer" onClick={() => setSortBy('output')}>خروجی/1M (تومان) {sortBy === 'output' && '↕'}</div>
          <div className="text-center">سطح</div>
        </div>

        {loading ? (
          <div className="p-5">
            {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => (
              <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '14px 0', borderBottom: i < 9 ? '1px solid var(--border)' : 'none' }}>
                <div className="skeleton" style={{ width: 36, height: 36, borderRadius: 'var(--radius-full)' }} />
                <div className="flex-1"><div className="skeleton" style={{ width: 140, height: 16, borderRadius: 'var(--radius-sm)' }} /></div>
                <div className="skeleton" className="w-20 h-4 rounded-sm" />
                <div className="skeleton" className="w-20 h-4 rounded-sm" />
                <div className="skeleton" className="w-20 h-4 rounded-sm" />
                <div className="skeleton" className="w-20 h-4 rounded-sm" />
                <div className="skeleton" style={{ width: 60, height: 20, borderRadius: 'var(--radius-full)' }} />
              </div>
            ))}
          </div>
        ) : models.length === 0 ? (
          <div className="p-12 text-center text-muted">
            <Icon name="info" size={32} className="mb-3 text-muted" />
            <p>مدلی یافت نشد</p>
          </div>
        ) : (
          sortedModels.map((model, idx) => {
            const tier = getModelTier(model.providerModelId)
            const icon = getModelIcon(model.providerModelId)
            const inputPct = (model.pricing.inputPerMillion / maxInput) * 100
            const outputPct = (model.pricing.outputPerMillion / maxOutput) * 100
            const usdInput = model.pricing.usd?.inputPerMillion ?? 0
            const usdOutput = model.pricing.usd?.outputPerMillion ?? 0

            return (
              <div
                key={model.id}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 130px 130px 130px 130px 90px',
                  gap: 8,
                  padding: '12px 16px',
                  borderBottom: idx < sortedModels.length - 1 ? '1px solid var(--border)' : 'none',
                  alignItems: 'center',
                  transition: 'background 0.15s ease',
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-hover)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
              >
                {/* Model name */}
                <div className="flex items-center gap-2.5">
                  <span className="text-[22px] leading-none">{icon}</span>
                  <div>
                    <div className="text-[13px] font-semibold text-primary">{model.displayName}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFeatureSettings: '"tnum"', direction: 'ltr', textAlign: 'left' }}>{model.providerModelId}</div>
                  </div>
                </div>

                {/* Input price USD */}
                <div className="text-start">
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', fontFeatureSettings: '"tnum"', direction: 'ltr' }}>{fmtUSD(usdInput)}</div>
                </div>

                {/* Input price Toman */}
                <div className="text-start">
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"', direction: 'ltr' }}>{fmtIRR(model.pricing.inputPerMillion)}</div>
                  <div style={{ marginTop: 3, height: 3, borderRadius: 2, background: 'var(--border)', overflow: 'hidden' }}>
                    <div style={{ width: `${inputPct}%`, height: '100%', borderRadius: 2, background: 'var(--accent)', opacity: 0.5 }} />
                  </div>
                </div>

                {/* Output price USD */}
                <div className="text-start">
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', fontFeatureSettings: '"tnum"', direction: 'ltr' }}>{fmtUSD(usdOutput)}</div>
                </div>

                {/* Output price Toman */}
                <div className="text-start">
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"', direction: 'ltr' }}>{fmtIRR(model.pricing.outputPerMillion)}</div>
                  <div style={{ marginTop: 3, height: 3, borderRadius: 2, background: 'var(--border)', overflow: 'hidden' }}>
                    <div style={{ width: `${outputPct}%`, height: '100%', borderRadius: 2, background: 'var(--warning)', opacity: 0.6 }} />
                  </div>
                </div>

                {/* Tier badge */}
                <div className="text-center">
                  <span style={{ fontSize: 10, fontWeight: 600, color: tier.color, background: `${tier.color}15`, padding: '3px 8px', borderRadius: 'var(--radius-full)' }}>{tier.label}</span>
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Info notes */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16, marginBottom: 40 }}>
        <div className="card" className="p-5">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Icon name="info" size={16} className="text-accent" />
            <span className="text-sm font-semibold text-primary">واحد قیمت</span>
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
            قیمتها به <strong>تومان</strong> و <strong>دلار</strong> به ازای هر <strong>۱ میلیون توکن</strong> هستند. یک پیام معمولی حدود ۵۰۰-۲۰۰۰ توکن مصرف می‌کند.
          </p>
        </div>
        <div className="card" className="p-5">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Icon name="wallet" size={16} className="text-accent" />
            <span className="text-sm font-semibold text-primary">شارژ کیف پول</span>
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
            کیف پول خود را شارژ کنید و به ازای مصرف واقعی هر پیام، هزینه از موجودی کسر می‌شود. بدون اشتراک ماهانه!
          </p>
        </div>
        <div className="card" className="p-5">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Icon name="sparkles" size={16} className="text-accent" />
            <span className="text-sm font-semibold text-primary">مدل هوشمند</span>
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
            با حالت «Smart»، سیستم بهترین مدل را بر اساس پیام شما انتخاب می‌کند تا بهترین کیفیت و هزینه را داشته باشید.
          </p>
        </div>
      </div>

      {/* Bottom CTA */}
      <div style={{
        textAlign: 'center',
        padding: '40px 24px',
        background: 'linear-gradient(135deg, rgba(124,111,247,0.08) 0%, rgba(103,232,249,0.04) 100%)',
        borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border)',
      }}>
        <Icon name="sparkles" size={28} className="text-accent mb-3" />
        <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>
          آماده شروع هستید؟
        </h3>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 20, maxWidth: 400, margin: '0 auto 20px' }}>
          کیف پول خود را شارژ کنید و همین الان با هوش مصنوعی چت کنید.
        </p>
        <div className="flex gap-3 justify-center flex-wrap">
          {!user ? (
            <Link href="/login" className="btn btn-primary" style={{ padding: '10px 28px', fontSize: 14, fontWeight: 600, borderRadius: 'var(--radius-md)', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <Icon name="profile" size={16} />
              ورود و شروع
            </Link>
          ) : (
            <Link href="/wallet" className="btn btn-primary" style={{ padding: '10px 28px', fontSize: 14, fontWeight: 600, borderRadius: 'var(--radius-md)', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <Icon name="wallet" size={16} />
              شارژ کیف پول
            </Link>
          )}
          <Link href="/chat" className="btn btn-secondary" style={{ padding: '10px 28px', fontSize: 14, fontWeight: 600, borderRadius: 'var(--radius-md)', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <Icon name="chat" size={16} />
            شروع چت رایگان
          </Link>
        </div>
      </div>
    </div>
  )
}
