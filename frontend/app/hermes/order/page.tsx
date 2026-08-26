'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { Icon } from '@/components/ui/Icon'
import { Spinner, toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { hermesOrderStrings } from './page.strings'

/* ═══════════════════════════════════════════════════════════════
   Order wizard: pick a server offering, attach skills (with options
   rendered straight from each skill's options_schema), review the
   Toman invoice, then hand off to Zarinpal.
   ═══════════════════════════════════════════════════════════════ */

type Offering = {
  id: string
  name_fa: string
  name_en: string
  vcpu: number
  ram_mb: number
  max_skills: number
  setup_price_irt: number
  monthly_price_irt: number
}

type OptionField = {
  type: 'multiselect' | 'tags' | 'cron' | string
  values?: string[]
  max?: number
  default?: unknown
}

type SkillCatalogItem = {
  id: string
  name_fa: string
  name_en: string
  description_fa: string
  description_en: string
  category: string
  options_schema: Record<string, OptionField>
  requires_cron: boolean
}

type SelectedSkill = {
  skill_id: string
  options: Record<string, unknown>
}

export default function HermesOrderPage() {
  const { token, user } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()
  const lang = useLang()
  const s = hermesOrderStrings(lang)
  const f = fmt(lang)
  const offeringName = (o: Offering) => (lang === 'en' ? o.name_en : o.name_fa)

  const [offerings, setOfferings] = useState<Offering[]>([])
  const [catalog, setCatalog] = useState<SkillCatalogItem[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [offeringId, setOfferingId] = useState(searchParams.get('offering') || '')
  const [selected, setSelected] = useState<SelectedSkill[]>([])

  // Payment-return banner. A declined/cancelled Hermes order redirects back
  // here with ?payment=failed (backend/payment_endpoints.py:148); nothing used
  // to read it, so the user landed on the order form with no explanation.
  const [paymentBanner, setPaymentBanner] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    const payment = searchParams.get('payment')
    let banner: { ok: boolean; text: string } | null = null
    if (payment === 'failed') {
      banner = { ok: false, text: s.paymentFailed }
    } else if (payment === 'error') {
      banner = { ok: false, text: s.paymentError }
    }
    if (banner) {
      setPaymentBanner(banner)
      const url = new URL(window.location.href)
      url.searchParams.delete('payment')
      window.history.replaceState(null, '', url.pathname + url.search + url.hash)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [offRes, skillRes] = await Promise.all([
          fetch('/api/hermes/offerings'),
          fetch('/api/hermes/skill-catalog'),
        ])
        const offData = offRes.ok ? await offRes.json() : []
        const skillData = skillRes.ok ? await skillRes.json() : []
        if (cancelled) return
        setOfferings(Array.isArray(offData) ? offData : [])
        setCatalog(Array.isArray(skillData) ? skillData : [])
        if (!offeringId && offData?.length) setOfferingId(offData[0].id)
      } catch {
        if (!cancelled) toast(s.loadError, 'error')
      } finally {
        if (!cancelled) setLoading(false)
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    })()
    return () => { cancelled = true }
  }, [])

  const offering = useMemo(() => offerings.find((o) => o.id === offeringId) ?? null, [offerings, offeringId])

  const total = (offering?.setup_price_irt ?? 0) + (offering?.monthly_price_irt ?? 0)

  const toggleSkill = (skillId: string) => {
    setSelected((prev) => {
      if (prev.some((s) => s.skill_id === skillId)) {
        return prev.filter((s) => s.skill_id !== skillId)
      }
      if (offering && prev.length >= offering.max_skills) {
        toast(s.maxSkillsReached(f.num(offering.max_skills)), 'error')
        return prev
      }
      return [...prev, { skill_id: skillId, options: {} }]
    })
  }

  const setSkillOption = (skillId: string, key: string, value: unknown) => {
    setSelected((prev) => prev.map((s) => (s.skill_id === skillId ? { ...s, options: { ...s.options, [key]: value } } : s)))
  }

  const handleSubmit = async () => {
    if (!offering) return
    setSubmitting(true)
    try {
      const res = await apiFetch('/api/hermes/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ offering_id: offering.id, config: { skills: selected } }),
      })
      const data = await res.json()
      if (!res.ok) {
        toast(data?.detail || s.submitError, 'error')
        return
      }
      if (data.url) {
        window.location.href = data.url
      } else {
        router.push(`/hermes/orders`)
      }
    } catch {
      toast(s.networkError, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  if (!user) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '50vh', gap: '1rem' }}>
        <h1 className="page-title">{s.signIn}</h1>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>{s.loginPrompt}</p>
        <a href="/login" className="btn btn-primary">{s.loginToAccount}</a>
      </div>
    )
  }

  if (loading) {
    return <div className="flex items-center justify-center" style={{ minHeight: '40vh' }}><Spinner size="lg" /></div>
  }

  return (
    <div className="flex flex-col gap-6" style={{ maxWidth: '48rem' }}>
      <h1 className="page-title">{s.pageTitle}</h1>

      {/* Payment-return banner */}
      {paymentBanner && (
        <div
          role="status"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            padding: '0.875rem 1rem',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--danger)',
            background: 'color-mix(in srgb, var(--danger) 12%, transparent)',
          }}
        >
          <span style={{ flexShrink: 0, color: 'var(--danger)' }}>
            <Icon name="warning" size={18} />
          </span>
          <span style={{ flex: 1, fontSize: '0.875rem', color: 'var(--text-primary)' }}>{paymentBanner.text}</span>
          <button
            onClick={() => setPaymentBanner(null)}
            aria-label={s.close}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4, display: 'inline-flex' }}
          >
            <Icon name="close" size={16} />
          </button>
        </div>
      )}

      {/* ── Step 1: offering ── */}
      <section className="card" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <h2 style={{ fontWeight: 700 }}>{s.step1Title(f.num(1))}</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
          {offerings.map((o) => (
            <button
              key={o.id}
              onClick={() => { setOfferingId(o.id); setSelected([]) }}
              className={`btn ${o.id === offeringId ? 'btn-primary' : 'btn-secondary'} btn-sm`}
            >
              {offeringName(o)} — {f.price(o.monthly_price_irt)}{s.perMonth}
            </button>
          ))}
        </div>
      </section>

      {/* ── Step 2: skills ── */}
      <section className="card" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <h2 style={{ fontWeight: 700 }}>
          {s.step2Title(f.num(2))} {offering && <span style={{ fontWeight: 400, fontSize: '0.75rem', color: 'var(--text-muted)' }}>{s.maxSkillsHint(f.num(offering.max_skills))}</span>}
        </h2>
        <div className="flex flex-col gap-3">
          {catalog.map((skill) => (
            <SkillPicker
              key={skill.id}
              skill={skill}
              checked={selected.some((sel) => sel.skill_id === skill.id)}
              options={selected.find((sel) => sel.skill_id === skill.id)?.options ?? {}}
              onToggle={() => toggleSkill(skill.id)}
              onOptionChange={(key, value) => setSkillOption(skill.id, key, value)}
            />
          ))}
        </div>
      </section>

      {/* ── Step 3: invoice ── */}
      <section className="card" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <h2 style={{ fontWeight: 700 }}>{s.step3Title(f.num(3))}</h2>
        {offering && (
          <>
            {offering.setup_price_irt > 0 && (
              <div className="flex items-center justify-between" style={{ fontSize: '0.875rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>{s.setupCost}</span>
                <span>{f.price(offering.setup_price_irt)}</span>
              </div>
            )}
            <div className="flex items-center justify-between" style={{ fontSize: '0.875rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>{s.firstMonth}</span>
              <span>{f.price(offering.monthly_price_irt)}</span>
            </div>
            <div className="flex items-center justify-between" style={{ borderTop: '1px solid var(--border)', paddingTop: '0.5rem', fontWeight: 700 }}>
              <span>{s.totalPayable}</span>
              <span style={{ color: 'var(--accent)' }}>{f.price(total)}</span>
            </div>
          </>
        )}
        <button className="btn btn-primary" disabled={!offering || submitting} onClick={handleSubmit} style={{ marginTop: '0.75rem', justifyContent: 'center' }}>
          {submitting ? <Spinner size="sm" /> : <Icon name="payment" size={16} />}
          {s.payAndSubmit}
        </button>
      </section>
    </div>
  )
}

function SkillPicker({
  skill, checked, options, onToggle, onOptionChange,
}: {
  skill: SkillCatalogItem
  checked: boolean
  options: Record<string, unknown>
  onToggle: () => void
  onOptionChange: (key: string, value: unknown) => void
}) {
  const lang = useLang()
  const name = lang === 'en' ? skill.name_en : skill.name_fa
  const description = lang === 'en' ? skill.description_en : skill.description_fa
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '0.875rem' }}>
      <label className="flex items-center gap-2" style={{ cursor: 'pointer' }}>
        <input
          type="checkbox"
          checked={checked}
          onChange={onToggle}
          style={{ width: '1.5rem', height: '1.5rem', accentColor: 'var(--accent)', flexShrink: 0 }}
        />
        <span style={{ fontWeight: 600 }}>{name}</span>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{description}</span>
      </label>

      {checked && (
        <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.5rem', paddingRight: '1.5rem' }}>
          {Object.entries(skill.options_schema || {}).map(([key, field]) => (
            <OptionInput key={key} fieldKey={key} field={field} value={options[key]} onChange={(v) => onOptionChange(key, v)} />
          ))}
        </div>
      )}
    </div>
  )
}

function OptionInput({
  fieldKey, field, value, onChange,
}: {
  fieldKey: string
  field: OptionField
  value: unknown
  onChange: (value: unknown) => void
}) {
  const lang = useLang()
  const s = hermesOrderStrings(lang)
  const f = fmt(lang)

  if (field.type === 'multiselect' && field.values) {
    const current = Array.isArray(value) ? (value as string[]) : []
    return (
      <div>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>{fieldKey}</span>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>
          {field.values.map((v) => {
            const active = current.includes(v)
            return (
              <button
                key={v}
                type="button"
                className={`btn ${active ? 'btn-primary' : 'btn-secondary'} btn-sm`}
                onClick={() => {
                  if (active) {
                    onChange(current.filter((c) => c !== v))
                  } else if (!field.max || current.length < field.max) {
                    onChange([...current, v])
                  } else {
                    toast(s.maxOptionsReached(f.num(field.max)), 'error')
                  }
                }}
                style={{ fontSize: '0.75rem', padding: '0.25rem 0.625rem' }}
              >
                {v}
              </button>
            )
          })}
        </div>
      </div>
    )
  }

  if (field.type === 'tags') {
    // Arabic/Persian comma (U+060C) when joining for display in a Persian UI,
    // plain comma in English; written as an escape rather than the literal
    // character so it reads as the delimiter it is, not a translatable
    // string the coverage scanner (tests/lib/productI18nCoverage.test.ts)
    // should flag. The split on blur accepts either regardless of `lang`, so
    // switching languages mid-edit never breaks parsing.
    const joiner = lang === 'en' ? ', ' : '\u060C '
    const current = Array.isArray(value) ? (value as string[]).join(joiner) : ''
    return (
      <div>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>{fieldKey} {s.commaSeparated}</span>
        <input
          type="text"
          defaultValue={current}
          onBlur={(e) => {
            const tags = e.target.value.split(/[\u060C,]/).map((t) => t.trim()).filter(Boolean)
            onChange(field.max ? tags.slice(0, field.max) : tags)
          }}
          className="input"
          style={{ width: '100%' }}
        />
      </div>
    )
  }

  if (field.type === 'cron') {
    return (
      <div>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>{s.schedule}</span>
        <input
          type="text"
          defaultValue={typeof value === 'string' ? value : (field.default as string) || '0 9 * * *'}
          onBlur={(e) => onChange(e.target.value)}
          className="input"
          style={{ width: '100%', fontFamily: 'monospace', direction: 'ltr', textAlign: 'left' }}
        />
      </div>
    )
  }

  return null
}
