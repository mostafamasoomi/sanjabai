'use client'

import { Icon } from '@/components/ui/Icon'
import { Field, NumInput } from './shared'
import { isLossPath, type NewPackageDraft } from './PackagesTypes'

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
  const set = <K extends keyof NewPackageDraft>(field: K, value: NewPackageDraft[K]) =>
    setNewPackage({ ...newPackage, [field]: value })

  return (
    <div className="mt-3 space-y-3">
      <div className="flex flex-wrap gap-3 items-end">
        <Field label="شناسه (id)">
          <input className="input" dir="ltr" value={newPackage.id}
            onChange={(e) => set('id', e.target.value)} style={{ maxWidth: 140 }} />
        </Field>
        <Field label="نام فارسی">
          <input className="input" value={newPackage.name_fa}
            onChange={(e) => set('name_fa', e.target.value)} style={{ maxWidth: 150 }} />
        </Field>
        <Field label="نام انگلیسی">
          <input className="input" value={newPackage.name_en}
            onChange={(e) => set('name_en', e.target.value)} style={{ maxWidth: 150 }} />
        </Field>
        <Field label="فعال">
          <input type="checkbox" checked={newPackage.active}
            onChange={(e) => set('active', e.target.checked)} />
        </Field>
      </div>
      <div className="flex flex-wrap gap-3 items-end">
        <Field label="مبلغ پرداختی">
          <NumInput value={newPackage.base_amount} onChange={(v) => set('base_amount', v)} />
        </Field>
        <Field label="مبلغ واریزی به کیف پول">
          <NumInput value={newPackage.total_credits} onChange={(v) => set('total_credits', v)} />
        </Field>
        <Field label="درصد پاداش">
          <NumInput value={newPackage.bonus_percent} onChange={(v) => set('bonus_percent', v)} width={80} />
        </Field>
        <Field label="سهمیهٔ درخواست">
          <NumInput value={newPackage.request_quota} onChange={(v) => set('request_quota', v)} placeholder="بدون سهمیه" />
        </Field>
        <Field label="سهمیهٔ توکن">
          <NumInput value={newPackage.token_quota} onChange={(v) => set('token_quota', v)} placeholder="بدون سهمیه" />
        </Field>
        <Field label="سقف هزینهٔ هر درخواست">
          <NumInput value={newPackage.max_cost_per_request_toman} onChange={(v) => set('max_cost_per_request_toman', v)} placeholder="بدون سقف" />
        </Field>
      </div>
      <div className="flex flex-wrap gap-3 items-end">
        <Field label="سقف پیام (۵ ساعته)">
          <NumInput value={newPackage.rate_limit_per_window} onChange={(v) => set('rate_limit_per_window', v)} placeholder="بدون سقف" />
        </Field>
        <Field label="از این، روی مدل گران (۵ ساعته)">
          <NumInput value={newPackage.premium_rate_limit_per_window} onChange={(v) => set('premium_rate_limit_per_window', v)} placeholder="بدون سقف" />
        </Field>
        <Field label="مدت اعتبار (روز)">
          <NumInput value={newPackage.validity_days} onChange={(v) => set('validity_days', v)} width={90} placeholder="بدون انقضا" />
        </Field>
      </div>
      {isLossPath(newPackage) && (
        <div className="text-xs flex items-center gap-1" style={{ color: 'var(--warning, #f59e0b)' }}>
          <Icon name="warning" size={12} />
          <span>سهمیه بدون سقف هزینه — سرور این را رد می‌کند</span>
        </div>
      )}
      <button className="btn btn-sm" onClick={onCreate} disabled={creating}>
        {creating ? 'در حال ایجاد...' : 'ایجاد بسته'}
      </button>
    </div>
  )
}
