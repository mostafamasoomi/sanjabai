'use client'

import { useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { SectionHeader, Field } from './shared'
import { ErrorCard, RefreshButton, CardSkeleton } from './LoadState'
import { api, errMessage } from '../api'
import { useAdminResource } from '../useAdminResource'
import type { FeatureRow } from '../types'
import { featuresStrings } from './FeaturesSection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Features — self-contained. GET/POST /admin/features, DELETE
   /admin/features/{id} (backend/admin_content.py).
   ═══════════════════════════════════════════════════════════════════════════ */

export default function FeaturesSection() {
  const lang = useLang()
  const s = featuresStrings(lang)
  const f = fmt(lang)

  const { data: features, error, loading, reload } = useAdminResource<FeatureRow[]>(
    '/api/admin/features',
    (raw) => (Array.isArray(raw) ? raw : raw?.features || []),
    s.loadError,
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
      toast(ftId ? s.saveEditSuccess : s.saveAddSuccess, 'success')
      resetFeatureForm()
      reload()
    } catch (err) {
      toast(errMessage(err, s.saveError), 'error')
    } finally {
      setSaving(false)
    }
  }

  const delFeature = async (id: number) => {
    try {
      await api('/api/admin/features/' + id, { method: 'DELETE' })
      toast(s.deleteSuccess, 'success')
      reload()
    } catch (err) {
      toast(errMessage(err, s.deleteError), 'error')
    }
  }

  const list = features || []

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <SectionHeader title={s.title} subtitle={s.subtitle(f.num(list.length))} />
        <RefreshButton onClick={reload} busy={loading} />
      </div>

      {error && <ErrorCard message={error} onRetry={reload} />}
      {!error && !features && <CardSkeleton count={3} />}

      {features && (
        <div className="space-y-2">
          {list.length === 0 && (
            <div className="admin-card text-center py-8 text-muted">
              {s.noneRegistered}
            </div>
          )}
          {/* f.title / f.description here are the saved feature copy, from
              and to the server — content, not UI chrome, so left as-is. */}
          {list.map((row) => (
            <div key={row.id} className="admin-card admin-row justify-between">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm" style={{ background: 'var(--bg-elevated)' }}>
                  {row.icon || '—'}
                </div>
                <div>
                  <p className="text-sm font-medium text-primary">{row.title}</p>
                  <p className="text-xs text-muted">{row.description || s.noDescription}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={row.active ? 'badge badge-positive' : 'badge badge-warning'}>
                  {row.active ? s.active : s.disabled}
                </span>
                <span className="badge text-[10px]">#{f.num(row.order_idx)}</span>
                <button className="btn btn-sm" onClick={() => editFeature(row)}>
                  <Icon name="settings" size={14} />
                </button>
                <button className="btn btn-sm btn-danger" onClick={() => delFeature(row.id)}>
                  <Icon name="close" size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="admin-card">
        <h3 className="font-semibold text-sm mb-4 text-primary">
          {ftId ? s.editTitle : s.addTitle}
        </h3>
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label={s.titleField}>
              <input className="input w-full" value={ftTitle} onChange={(e) => setFtTitle(e.target.value)} placeholder={s.titlePlaceholder} />
            </Field>
            <Field label={s.iconField}>
              <input className="input w-full" value={ftIcon} onChange={(e) => setFtIcon(e.target.value)} placeholder="icon-name" />
            </Field>
          </div>
          <Field label={s.descriptionField}>
            <textarea className="input w-full min-h-[80px] resize-y" value={ftDesc} onChange={(e) => setFtDesc(e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label={s.orderField}>
              <input className="input w-full" type="number" value={ftOrder} onChange={(e) => setFtOrder(e.target.value)} />
            </Field>
            <Field label={s.statusField}>
              <select className="input w-full" value={String(ftActive)} onChange={(e) => setFtActive(e.target.value === 'true')}>
                <option value="true">{s.active}</option>
                <option value="false">{s.disabled}</option>
              </select>
            </Field>
          </div>
        </div>
        <div className="flex gap-2 mt-4">
          <button className="btn" onClick={saveFeature} disabled={saving}>
            {saving ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
            ) : (<><Icon name="check" size={16} /><span>{ftId ? s.update : s.add}</span></>)}
          </button>
          {ftId && (
            <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={resetFeatureForm}>
              {s.cancel}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
