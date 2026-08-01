'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { Spinner, toast } from '@/components/ui'
import { faPrice, faNum } from '@/lib/format'

/* ═══════════════════════════════════════════════════════════════
   Order wizard: pick a server offering, attach skills (with options
   rendered straight from each skill's options_schema), review the
   Toman invoice, then hand off to Zarinpal.
   ═══════════════════════════════════════════════════════════════ */

type Offering = {
  id: string
  name_fa: string
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
  description_fa: string
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

  const [offerings, setOfferings] = useState<Offering[]>([])
  const [catalog, setCatalog] = useState<SkillCatalogItem[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [offeringId, setOfferingId] = useState(searchParams.get('offering') || '')
  const [selected, setSelected] = useState<SelectedSkill[]>([])

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
        if (!cancelled) toast('خطا در دریافت اطلاعات سرویس', 'error')
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
        toast(`این پلن حداکثر ${offering.max_skills} اسکیل پشتیبانی می‌کند`, 'error')
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
      const res = await fetch('/api/hermes/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ offering_id: offering.id, config: { skills: selected } }),
      })
      const data = await res.json()
      if (!res.ok) {
        toast(data?.detail || 'خطا در ثبت سفارش', 'error')
        return
      }
      if (data.url) {
        window.location.href = data.url
      } else {
        router.push(`/hermes/orders`)
      }
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  if (!user) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '50vh', gap: '1rem' }}>
        <h1 className="page-title">وارد شوید</h1>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>برای سفارش سرور هرمس ابتدا وارد حساب کاربری خود شوید.</p>
        <a href="/login" className="btn btn-primary">ورود به حساب</a>
      </div>
    )
  }

  if (loading) {
    return <div className="flex items-center justify-center" style={{ minHeight: '40vh' }}><Spinner size="lg" /></div>
  }

  return (
    <div className="flex flex-col gap-6" style={{ maxWidth: '48rem' }}>
      <h1 className="page-title">سفارش سرور هرمس</h1>

      {/* ── Step 1: offering ── */}
      <section className="card" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <h2 style={{ fontWeight: 700 }}>۱. انتخاب پلن سرور</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
          {offerings.map((o) => (
            <button
              key={o.id}
              onClick={() => { setOfferingId(o.id); setSelected([]) }}
              className={`btn ${o.id === offeringId ? 'btn-primary' : 'btn-secondary'} btn-sm`}
            >
              {o.name_fa} — {faPrice(o.monthly_price_irt)}/ماه
            </button>
          ))}
        </div>
      </section>

      {/* ── Step 2: skills ── */}
      <section className="card" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <h2 style={{ fontWeight: 700 }}>
          ۲. انتخاب اسکیل‌ها {offering && <span style={{ fontWeight: 400, fontSize: '0.75rem', color: 'var(--text-muted)' }}>(حداکثر {faNum(offering.max_skills)})</span>}
        </h2>
        <div className="flex flex-col gap-3">
          {catalog.map((skill) => (
            <SkillPicker
              key={skill.id}
              skill={skill}
              checked={selected.some((s) => s.skill_id === skill.id)}
              options={selected.find((s) => s.skill_id === skill.id)?.options ?? {}}
              onToggle={() => toggleSkill(skill.id)}
              onOptionChange={(key, value) => setSkillOption(skill.id, key, value)}
            />
          ))}
        </div>
      </section>

      {/* ── Step 3: invoice ── */}
      <section className="card" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <h2 style={{ fontWeight: 700 }}>۳. فاکتور</h2>
        {offering && (
          <>
            {offering.setup_price_irt > 0 && (
              <div className="flex items-center justify-between" style={{ fontSize: '0.875rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>هزینه راه‌اندازی</span>
                <span>{faPrice(offering.setup_price_irt)}</span>
              </div>
            )}
            <div className="flex items-center justify-between" style={{ fontSize: '0.875rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>ماه اول</span>
              <span>{faPrice(offering.monthly_price_irt)}</span>
            </div>
            <div className="flex items-center justify-between" style={{ borderTop: '1px solid var(--border)', paddingTop: '0.5rem', fontWeight: 700 }}>
              <span>مجموع پرداختی</span>
              <span style={{ color: 'var(--accent)' }}>{faPrice(total)}</span>
            </div>
          </>
        )}
        <button className="btn btn-primary" disabled={!offering || submitting} onClick={handleSubmit} style={{ marginTop: '0.75rem', justifyContent: 'center' }}>
          {submitting ? <Spinner size="sm" /> : <Icon name="payment" size={16} />}
          پرداخت و ثبت سفارش
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
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '0.875rem' }}>
      <label className="flex items-center gap-2" style={{ cursor: 'pointer' }}>
        <input
          type="checkbox"
          checked={checked}
          onChange={onToggle}
          style={{ width: '1.5rem', height: '1.5rem', accentColor: 'var(--accent)', flexShrink: 0 }}
        />
        <span style={{ fontWeight: 600 }}>{skill.name_fa}</span>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{skill.description_fa}</span>
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
                    toast(`حداکثر ${field.max} مورد قابل انتخاب است`, 'error')
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
    const current = Array.isArray(value) ? (value as string[]).join('، ') : ''
    return (
      <div>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>{fieldKey} (با ، جدا کنید)</span>
        <input
          type="text"
          defaultValue={current}
          onBlur={(e) => {
            const tags = e.target.value.split(/[،,]/).map((t) => t.trim()).filter(Boolean)
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
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>زمان‌بندی (cron)</span>
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
