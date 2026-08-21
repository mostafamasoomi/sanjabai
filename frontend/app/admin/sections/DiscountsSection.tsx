'use client'

import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { SectionHeader, Field } from './shared'
import type { DiscountRow } from '../AdminPanel'

/* ═══════════════════════════════════════════════════════════════════════════
   Discounts — moved verbatim out of AdminPanel.tsx (page === 'discounts').
   All state and handlers still live in AdminPanel; this component is purely
   presentational.
   ═══════════════════════════════════════════════════════════════════════════ */

interface DiscountsSectionProps {
  discounts: DiscountRow[]
  dcId: string
  dcCode: string
  setDcCode: (v: string) => void
  dcPercent: string
  setDcPercent: (v: string) => void
  dcActive: boolean
  setDcActive: (v: boolean) => void
  saveDiscount: () => void
  editDiscount: (d: DiscountRow) => void
  delDiscount: (id: number) => void
  resetDiscountForm: () => void
}

export default function DiscountsSection({
  discounts, dcId, dcCode, setDcCode, dcPercent, setDcPercent, dcActive, setDcActive,
  saveDiscount, editDiscount, delDiscount, resetDiscountForm,
}: DiscountsSectionProps) {
  return (
    <div className="space-y-6">
      <SectionHeader title="کدهای تخفیف" subtitle={`${faNum(discounts.length)} کد تخفیف فعال`} />

      <div className="space-y-2">
        {discounts.length === 0 && (
          <div className="admin-card text-center py-8 text-muted">
            کد تخفیفی ثبت نشده
          </div>
        )}
        {discounts.map((d) => (
          <div key={d.id} className="admin-card flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="px-3 py-1.5 rounded-lg font-mono text-sm font-bold" style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}>
                {d.code}
              </div>
              <span className="text-sm text-primary">{d.percent}%</span>
            </div>
            <div className="flex items-center gap-2">
              <span className={d.active ? 'badge badge-positive' : 'badge badge-warning'}>
                {d.active ? 'فعال' : 'غیرفعال'}
              </span>
              <button className="btn btn-sm" onClick={() => editDiscount(d)}>
                <Icon name="settings" size={14} />
              </button>
              <button className="btn btn-sm btn-danger" onClick={() => delDiscount(d.id)}>
                <Icon name="close" size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="admin-card">
        <h3 className="font-semibold text-sm mb-4 text-primary">
          {dcId ? 'ویرایش کد تخفیف' : 'افزودن کد تخفیف'}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Field label="کد تخفیف">
            <input className="input w-full" value={dcCode} onChange={(e) => setDcCode(e.target.value)} placeholder="WELCOME10" />
          </Field>
          <Field label="درصد تخفیف">
            <input className="input w-full" type="number" value={dcPercent} onChange={(e) => setDcPercent(e.target.value)} />
          </Field>
          <Field label="وضعیت">
            <select className="input w-full" value={String(dcActive)} onChange={(e) => setDcActive(e.target.value === 'true')}>
              <option value="true">فعال</option>
              <option value="false">غیرفعال</option>
            </select>
          </Field>
        </div>
        <div className="flex gap-2 mt-4">
          <button className="btn" onClick={saveDiscount}>
            <Icon name="check" size={16} />
            <span>{dcId ? 'بروزرسانی' : 'افزودن'}</span>
          </button>
          {dcId && (
            <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={resetDiscountForm}>
              انصراف
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
