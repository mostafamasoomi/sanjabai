'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { Num } from '@/lib/format'

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
  if (modelId.includes('large') || modelId.includes('medium')) return { label: 'حرفه‌ای', color: 'var(--accent)' }
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
      toast('خطا در دریافت اطلاعات مدل‌ها', 'error')
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

      {/* Hero — staggered entrance so the pill, headline, and subtext settle
          in sequence instead of the whole block popping in at once. */}
      <div style={{ textAlign: 'center', marginBottom: 48 }}>
        <div className="slide-up" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 16px', borderRadius: 'var(--radius-full)', background: 'var(--accent-dim)', marginBottom: 20 }}>
          <Icon name="sparkles" size={16} className="text-accent" />
          <span style={{ fontSize: 13, color: 'var(--accent)', fontWeight: 600 }}>تعرفه مدل‌ها</span>
        </div>
        <h1 className="slide-up" style={{ fontSize: 'var(--fs-3xl)', fontWeight: 800, color: 'var(--text-primary)', marginBottom: 12, lineHeight: 1.4, animationDelay: '0.05s' }}>
          قیمت‌گذاری شفاف، پرداخت به ازای مصرف
        </h1>
        <p className="slide-up" style={{ fontSize: 15, color: 'var(--text-secondary)', maxWidth: 560, margin: '0 auto', lineHeight: 1.7, animationDelay: '0.1s' }}>
          هر مدل هوش مصنوعی قیمت مشخصی دارد. فقط به اندازه مصرف واقعی خود پرداخت کنید. قیمت‌ها به تومان به ازای هر ۱ میلیون توکن هستند.
        </p>
      </div>

      {/* Balance card (if logged in) */}
      {user && balance !== null && (
        <div className="card slide-up" style={{ padding: '16px 20px', marginBottom: 24, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, animationDelay: '0.15s' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon name="wallet" size={18} className="text-accent" />
            <span style={{ fontSize: 14, color: 'var(--text-secondary)' }}>موجودی کیف پول:</span>
            <Num className="text-lg font-bold" value={balance} unit="تومان" />
          </div>
          <Link href="/wallet" className="btn btn-sm btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Icon name="plus" size={14} />
            شارژ کیف پول
          </Link>
        </div>
      )}

      {/* Pricing Table */}
      <div className="card slide-up" style={{ overflow: 'hidden', marginBottom: 32, animationDelay: '0.2s' }}>
        {/* Table Header */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 130px 130px 90px', gap: 8, padding: '14px 16px', borderBottom: '2px solid var(--border)', background: 'var(--bg-hover)', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>
          {/* Real <button>s, not divs with role="button": these actually sort,
              so they need to be keyboard-operable, and aria-sort tells a
              screen-reader user which column is active. */}
          <button
            type="button"
            className="pricing-sort-btn"
            aria-pressed={sortBy === 'name'}
            onClick={() => setSortBy('name')}
          >
            مدل {sortBy === 'name' && '↕'}
          </button>
          <button
            type="button"
            className="pricing-sort-btn"
            aria-pressed={sortBy === 'input'}
            onClick={() => setSortBy('input')}
          >
            ورودی/میلیون {sortBy === 'input' && '↕'}
          </button>
          <button
            type="button"
            className="pricing-sort-btn"
            aria-pressed={sortBy === 'output'}
            onClick={() => setSortBy('output')}
          >
            خروجی/میلیون {sortBy === 'output' && '↕'}
          </button>
          <div className="text-center">سطح</div>
        </div>

        {loading ? (
          <div style={{ padding: 20 }}>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => (
              <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '14px 0', borderBottom: i < 9 ? '1px solid var(--border)' : 'none' }}>
                <div className="skeleton" style={{ width: 36, height: 36, borderRadius: 'var(--radius-full)' }} />
                <div className="flex-1"><div className="skeleton" style={{ width: 140, height: 16, borderRadius: 'var(--radius-sm)' }} /></div>
                <div className="skeleton" style={{ width: 80, height: 16, borderRadius: 'var(--radius-sm)' }} />
                <div className="skeleton" style={{ width: 80, height: 16, borderRadius: 'var(--radius-sm)' }} />
                <div className="skeleton" style={{ width: 80, height: 16, borderRadius: 'var(--radius-sm)' }} />
                <div className="skeleton" style={{ width: 80, height: 16, borderRadius: 'var(--radius-sm)' }} />
                <div className="skeleton" style={{ width: 60, height: 20, borderRadius: 'var(--radius-full)' }} />
              </div>
            ))}
          </div>
        ) : models.length === 0 ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)' }}>
            <Icon name="info" size={32} style={{ marginBottom: 12, color: 'var(--text-muted)' }} />
            <p>مدلی یافت نشد</p>
          </div>
        ) : (
          sortedModels.map((model, idx) => {
            const tier = getModelTier(model.providerModelId)
            const icon = getModelIcon(model.providerModelId)
            const inputPct = (model.pricing.inputPerMillion / maxInput) * 100
            const outputPct = (model.pricing.outputPerMillion / maxOutput) * 100

            return (
              <div
                key={model.id}
                className="pricing-row slide-up"
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 130px 130px 90px',
                  gap: 8,
                  padding: '12px 16px',
                  borderBottom: idx < sortedModels.length - 1 ? '1px solid var(--border)' : 'none',
                  alignItems: 'center',
                  animationDelay: `${0.25 + Math.min(idx, 10) * 0.03}s`,
                }}
              >
                {/* Model name */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 22, lineHeight: 1 }}>{icon}</span>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{model.displayName}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFeatureSettings: '"tnum"', direction: 'ltr', textAlign: 'left' }}>{model.providerModelId}</div>
                  </div>
                </div>

                {/* Input price, tomans per million tokens */}
                <div>
                  <Num className="pricing-cell-value" value={model.pricing.inputPerMillion} />
                  <div style={{ marginTop: 3, height: 3, borderRadius: 2, background: 'var(--border)', overflow: 'hidden' }}>
                    <div style={{ width: `${inputPct}%`, height: '100%', borderRadius: 2, background: 'var(--accent)', opacity: 0.5 }} />
                  </div>
                </div>

                {/* Output price, tomans per million tokens */}
                <div>
                  <Num className="pricing-cell-value" value={model.pricing.outputPerMillion} />
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
        <div className="card slide-up" style={{ padding: 20, animationDelay: '0.3s' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Icon name="info" size={16} className="text-accent" />
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>واحد قیمت</span>
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
            قیمت‌ها به <strong>تومان</strong> به ازای هر <strong>۱ میلیون توکن</strong> هستند. یک پیام معمولی حدود ۵۰۰-۲۰۰۰ توکن مصرف می‌کند.
          </p>
        </div>
        <div className="card slide-up" style={{ padding: 20, animationDelay: '0.35s' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Icon name="wallet" size={16} className="text-accent" />
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>شارژ کیف پول</span>
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
            کیف پول خود را شارژ کنید و به ازای مصرف واقعی هر پیام، هزینه از موجودی کسر می‌شود. بدون اشتراک ماهانه!
          </p>
        </div>
        <div className="card slide-up" style={{ padding: 20, animationDelay: '0.4s' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Icon name="sparkles" size={16} className="text-accent" />
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>مدل هوشمند</span>
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
            با حالت «Smart»، سیستم بهترین مدل را بر اساس پیام شما انتخاب می‌کند تا بهترین کیفیت و هزینه را داشته باشید.
          </p>
        </div>
      </div>

      {/* Bottom CTA — was a hardcoded purple/cyan gradient left over from
          before the squirrel-brand redesign; every other accent on this page
          (and site-wide) is the warm rust --accent, so this section quietly
          broke the "one accent color per page" rule. Now tinted off the same
          token, via color-mix so it stays a soft wash rather than a solid
          fill. */}
      <div className="slide-up" style={{
        textAlign: 'center',
        padding: '40px 24px',
        background: 'linear-gradient(135deg, color-mix(in srgb, var(--accent) 12%, transparent) 0%, color-mix(in srgb, var(--accent) 4%, transparent) 100%)',
        borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border)',
        animationDelay: '0.45s',
      }}>
        <Icon name="sparkles" size={28} style={{ color: 'var(--accent)', marginBottom: 12 }} />
        {/* h2, not h3 — the only heading above it on this page is the h1. */}
        <h2 style={{ fontSize: 'var(--fs-lg)', fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>
          آماده شروع هستید؟
        </h2>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 20, maxWidth: 400, margin: '0 auto 20px' }}>
          کیف پول خود را شارژ کنید و همین الان با هوش مصنوعی چت کنید.
        </p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
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
