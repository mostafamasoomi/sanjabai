'use client'

import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { SectionHeader, Field } from './shared'
import type { FeatureRow } from '../AdminPanel'

/* ═══════════════════════════════════════════════════════════════════════════
   Features — moved verbatim out of AdminPanel.tsx (page === 'features').
   All state and handlers still live in AdminPanel; this component is purely
   presentational.
   ═══════════════════════════════════════════════════════════════════════════ */

interface FeaturesSectionProps {
  features: FeatureRow[]
  ftId: string
  ftTitle: string
  setFtTitle: (v: string) => void
  ftDesc: string
  setFtDesc: (v: string) => void
  ftIcon: string
  setFtIcon: (v: string) => void
  ftOrder: string
  setFtOrder: (v: string) => void
  ftActive: boolean
  setFtActive: (v: boolean) => void
  saveFeature: () => void
  editFeature: (f: FeatureRow) => void
  delFeature: (id: number) => void
  resetFeatureForm: () => void
}

export default function FeaturesSection({
  features, ftId, ftTitle, setFtTitle, ftDesc, setFtDesc, ftIcon, setFtIcon,
  ftOrder, setFtOrder, ftActive, setFtActive, saveFeature, editFeature, delFeature, resetFeatureForm,
}: FeaturesSectionProps) {
  return (
    <div className="space-y-6">
      <SectionHeader title="امکانات و ویژگی‌ها" subtitle={`${faNum(features.length)} ویژگی ثبت شده`} />

      <div className="space-y-2">
        {features.length === 0 && (
          <div className="admin-card text-center py-8 text-muted">
            ویژگی‌ای ثبت نشده
          </div>
        )}
        {features.map((f) => (
          <div key={f.id} className="admin-card flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm" style={{ background: 'var(--bg-elevated)' }}>
                {f.icon || '—'}
              </div>
              <div>
                <p className="text-sm font-medium text-primary">{f.title}</p>
                <p className="text-xs text-muted">{f.description || 'بدون توضیح'}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className={f.active ? 'badge badge-positive' : 'badge badge-warning'}>
                {f.active ? 'فعال' : 'غیرفعال'}
              </span>
              <span className="badge text-[10px]">#{f.order_idx}</span>
              <button className="btn btn-sm" onClick={() => editFeature(f)}>
                <Icon name="settings" size={14} />
              </button>
              <button className="btn btn-sm btn-danger" onClick={() => delFeature(f.id)}>
                <Icon name="close" size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="admin-card">
        <h3 className="font-semibold text-sm mb-4 text-primary">
          {ftId ? 'ویرایش ویژگی' : 'افزودن ویژگی جدید'}
        </h3>
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="عنوان">
              <input className="input w-full" value={ftTitle} onChange={(e) => setFtTitle(e.target.value)} placeholder="چت هوشمند" />
            </Field>
            <Field label="آیکون">
              <input className="input w-full" value={ftIcon} onChange={(e) => setFtIcon(e.target.value)} placeholder="icon-name" />
            </Field>
          </div>
          <Field label="توضیحات">
            <textarea className="input w-full min-h-[80px] resize-y" value={ftDesc} onChange={(e) => setFtDesc(e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="ترتیب نمایش">
              <input className="input w-full" type="number" value={ftOrder} onChange={(e) => setFtOrder(e.target.value)} />
            </Field>
            <Field label="وضعیت">
              <select className="input w-full" value={String(ftActive)} onChange={(e) => setFtActive(e.target.value === 'true')}>
                <option value="true">فعال</option>
                <option value="false">غیرفعال</option>
              </select>
            </Field>
          </div>
        </div>
        <div className="flex gap-2 mt-4">
          <button className="btn" onClick={saveFeature}>
            <Icon name="check" size={16} />
            <span>{ftId ? 'بروزرسانی' : 'افزودن'}</span>
          </button>
          {ftId && (
            <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={resetFeatureForm}>
              انصراف
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
