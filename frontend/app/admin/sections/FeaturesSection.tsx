'use client'

import { useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum } from '@/lib/format'
import { SectionHeader, Field } from './shared'
import { ErrorCard, RefreshButton, CardSkeleton } from './LoadState'
import { api, errMessage } from '../api'
import { useAdminResource } from '../useAdminResource'
import type { FeatureRow } from '../types'

/* ═══════════════════════════════════════════════════════════════════════════
   Features — self-contained. GET/POST /admin/features, DELETE
   /admin/features/{id} (backend/admin_content.py).
   ═══════════════════════════════════════════════════════════════════════════ */

export default function FeaturesSection() {
  const { data: features, error, loading, reload } = useAdminResource<FeatureRow[]>(
    '/api/admin/features',
    (raw) => (Array.isArray(raw) ? raw : raw?.features || []),
    'خطا در دریافت ویژگی‌ها',
  )

  const [ftId, setFtId] = useState('')
  const [ftTitle, setFtTitle] = useState('')
  const [ftDesc, setFtDesc] = useState('')
  const [ftIcon, setFtIcon] = useState('')
  const [ftOrder, setFtOrder] = useState('0')
  const [ftActive, setFtActive] = useState(true)
  const [saving, setSaving] = useState(false)

  const resetFeatureForm = () => {
    setFtId(''); setFtTitle(''); setFtDesc(''); setFtIcon(''); setFtOrder('0'); setFtActive(true)
  }

  const editFeature = (f: FeatureRow) => {
    setFtId(String(f.id)); setFtTitle(f.title); setFtDesc(f.description); setFtIcon(f.icon)
    setFtOrder(String(f.order_idx)); setFtActive(f.active)
  }

  const saveFeature = async () => {
    if (!ftTitle.trim()) return
    setSaving(true)
    try {
      await api('/api/admin/features', {
        method: 'POST',
        body: JSON.stringify({ id: ftId ? +ftId : undefined, title: ftTitle, description: ftDesc, icon: ftIcon, order_idx: +ftOrder || 0, active: ftActive }),
      })
      toast(ftId ? 'ویژگی ویرایش شد' : 'ویژگی اضافه شد', 'success')
      resetFeatureForm()
      reload()
    } catch (err) {
      toast(errMessage(err, 'خطا در ذخیره ویژگی'), 'error')
    } finally {
      setSaving(false)
    }
  }

  const delFeature = async (id: number) => {
    try {
      await api('/api/admin/features/' + id, { method: 'DELETE' })
      toast('ویژگی حذف شد', 'success')
      reload()
    } catch (err) {
      toast(errMessage(err, 'خطا در حذف ویژگی'), 'error')
    }
  }

  const list = features || []

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <SectionHeader title="امکانات و ویژگی‌ها" subtitle={`${faNum(list.length)} ویژگی ثبت شده`} />
        <RefreshButton onClick={reload} busy={loading} />
      </div>

      {error && <ErrorCard message={error} onRetry={reload} />}
      {!error && !features && <CardSkeleton count={3} />}

      {features && (
        <div className="space-y-2">
          {list.length === 0 && (
            <div className="admin-card text-center py-8 text-muted">
              ویژگی‌ای ثبت نشده
            </div>
          )}
          {list.map((f) => (
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
                <span className="badge text-[10px]">#{faNum(f.order_idx)}</span>
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
      )}

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
          <button className="btn" onClick={saveFeature} disabled={saving}>
            {saving ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
            ) : (<><Icon name="check" size={16} /><span>{ftId ? 'بروزرسانی' : 'افزودن'}</span></>)}
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
