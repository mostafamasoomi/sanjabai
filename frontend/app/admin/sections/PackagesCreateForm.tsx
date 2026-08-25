'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { Field, NumInput } from './shared'
import { isLossPath, type NewPackageDraft } from './PackagesTypes'
import { packagesCreateFormStrings } from './PackagesCreateForm.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   The "+ افزودن بسته" create form, extracted from PackagesSection.tsx so
   that file stays under the 500-line cap. Pure presentational component --
   the draft state and the actual POST live in the parent.
   ═══════════════════════════════════════════════════════════════════════════ */

interface PackagesCreateFormProps {
  newPackage: NewPackageDraft
  setNewPackage: (d: NewPackageDraft) => void
  creating: boolean
  onCreate: () => void
}

export default function PackagesCreateForm({ newPackage, setNewPackage, creating, onCreate }: PackagesCreateFormProps) {
  const lang = useLang()
  const s = packagesCreateFormStrings(lang)
  const set = <K extends keyof NewPackageDraft>(field: K, value: NewPackageDraft[K]) =>
    setNewPackage({ ...newPackage, [field]: value })

  return (
    <div className="mt-3 space-y-3">
      <div className="flex flex-wrap gap-3 items-end">
        <Field label={s.fieldId}>
          <input className="input" dir="ltr" value={newPackage.id}
            onChange={(e) => set('id', e.target.value)} style={{ maxWidth: 140 }} />
        </Field>
        <Field label={s.fieldNameFa}>
          <input className="input" value={newPackage.name_fa}
            onChange={(e) => set('name_fa', e.target.value)} style={{ maxWidth: 150 }} />
        </Field>
        <Field label={s.fieldNameEn}>
          <input className="input" value={newPackage.name_en}
            onChange={(e) => set('name_en', e.target.value)} style={{ maxWidth: 150 }} />
        </Field>
        <Field label={s.fieldActive}>
          <input type="checkbox" checked={newPackage.active}
            onChange={(e) => set('active', e.target.checked)} />
        </Field>
      </div>
      <div className="flex flex-wrap gap-3 items-end">
        <Field label={s.fieldBaseAmount}>
          <NumInput value={newPackage.base_amount} onChange={(v) => set('base_amount', v)} />
        </Field>
        <Field label={s.fieldTotalCredits}>
          <NumInput value={newPackage.total_credits} onChange={(v) => set('total_credits', v)} />
        </Field>
        <Field label={s.fieldBonusPercent}>
          <NumInput value={newPackage.bonus_percent} onChange={(v) => set('bonus_percent', v)} width={80} />
        </Field>
        <Field label={s.fieldRequestQuota}>
          <NumInput value={newPackage.request_quota} onChange={(v) => set('request_quota', v)} placeholder={s.noQuotaPlaceholder} />
        </Field>
        <Field label={s.fieldTokenQuota}>
          <NumInput value={newPackage.token_quota} onChange={(v) => set('token_quota', v)} placeholder={s.noQuotaPlaceholder} />
        </Field>
        <Field label={s.fieldMaxCostPerRequest}>
          <NumInput value={newPackage.max_cost_per_request_toman} onChange={(v) => set('max_cost_per_request_toman', v)} placeholder={s.noCeilingPlaceholder} />
        </Field>
      </div>
      <div className="flex flex-wrap gap-3 items-end">
        <Field label={s.fieldRateLimit}>
          <NumInput value={newPackage.rate_limit_per_window} onChange={(v) => set('rate_limit_per_window', v)} placeholder={s.noCeilingPlaceholder} />
        </Field>
        <Field label={s.fieldPremiumRateLimit}>
          <NumInput value={newPackage.premium_rate_limit_per_window} onChange={(v) => set('premium_rate_limit_per_window', v)} placeholder={s.noCeilingPlaceholder} />
        </Field>
        <Field label={s.fieldValidityDays}>
          <NumInput value={newPackage.validity_days} onChange={(v) => set('validity_days', v)} width={90} placeholder={s.noExpiryPlaceholder} />
        </Field>
      </div>
      {isLossPath(newPackage) && (
        <div className="text-xs flex items-center gap-1" style={{ color: 'var(--warning, #f59e0b)' }}>
          <Icon name="warning" size={12} />
          <span>{s.lossPathWarning}</span>
        </div>
      )}
      <button className="btn btn-sm" onClick={onCreate} disabled={creating}>
        {creating ? s.creating : s.createPackage}
      </button>
    </div>
  )
}
