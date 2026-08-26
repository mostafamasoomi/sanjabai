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
import type { DiscountRow } from '../types'
import { discountsStrings } from './DiscountsSection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Discounts — self-contained. GET/POST /admin/discounts, DELETE
   /admin/discounts/{id} (backend/admin_content.py).
   ═══════════════════════════════════════════════════════════════════════════ */

export default function DiscountsSection() {
  const lang = useLang()
  const s = discountsStrings(lang)
  const f = fmt(lang)

  const { data: discounts, error, loading, reload } = useAdminResource<DiscountRow[]>(
    '/api/admin/discounts',
    (raw) => (Array.isArray(raw) ? raw : raw?.discounts || []),
    s.loadError,
  )

  const [dcId, setDcId] = useState('')
  const [dcCode, setDcCode] = useState('')
  const [dcPercent, setDcPercent] = useState('10')
  const [dcActive, setDcActive] = useState(true)
  const [saving, setSaving] = useState(false)

  const resetDiscountForm = () => {
    setDcId(''); setDcCode(''); setDcPercent('10'); setDcActive(true)
  }

  const editDiscount = (d: DiscountRow) => {
    setDcId(String(d.id)); setDcCode(d.code); setDcPercent(String(d.percent)); setDcActive(d.active)
  }

  const saveDiscount = async () => {
    if (!dcCode.trim()) return
    setSaving(true)
    try {
      await api('/api/admin/discounts', {
        method: 'POST',
        body: JSON.stringify({ id: dcId ? +dcId : undefined, code: dcCode, percent: +dcPercent || 0, active: dcActive }),
      })
      toast(dcId ? s.saveEditSuccess : s.saveAddSuccess, 'success')
      resetDiscountForm()
      reload()
    } catch (err) {
      toast(errMessage(err, s.saveError), 'error')
    } finally {
      setSaving(false)
    }
  }

  const delDiscount = async (id: number) => {
    try {
      await api('/api/admin/discounts/' + id, { method: 'DELETE' })
      toast(s.deleteSuccess, 'success')
      reload()
    } catch (err) {
      toast(errMessage(err, s.deleteError), 'error')
    }
  }

  const list = discounts || []

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <SectionHeader title={s.title} subtitle={s.subtitle(f.num(list.length))} />
        <RefreshButton onClick={reload} busy={loading} />
      </div>

      {error && <ErrorCard message={error} onRetry={reload} />}
      {!error && !discounts && <CardSkeleton count={3} />}

      {discounts && (
        <div className="space-y-2">
          {list.length === 0 && (
            <div className="admin-card text-center py-8 text-muted">
              {s.noneRegistered}
            </div>
          )}
          {/* d.code is a server-issued discount code, not a UI label. */}
          {list.map((d) => (
            <div key={d.id} className="admin-card admin-row justify-between">
              <div className="flex items-center gap-3">
                <div className="px-3 py-1.5 rounded-lg font-mono text-sm font-bold" style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}>
                  {d.code}
                </div>
                <span className="text-sm text-primary">{f.percent(d.percent)}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className={d.active ? 'badge badge-positive' : 'badge badge-warning'}>
                  {d.active ? s.active : s.disabled}
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
      )}

      <div className="admin-card">
        <h3 className="font-semibold text-sm mb-4 text-primary">
          {dcId ? s.editTitle : s.addTitle}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Field label={s.codeField}>
            <input className="input w-full" value={dcCode} onChange={(e) => setDcCode(e.target.value)} placeholder="WELCOME10" />
          </Field>
          <Field label={s.percentField}>
            <input className="input w-full" type="number" value={dcPercent} onChange={(e) => setDcPercent(e.target.value)} />
          </Field>
          <Field label={s.statusField}>
            <select className="input w-full" value={String(dcActive)} onChange={(e) => setDcActive(e.target.value === 'true')}>
              <option value="true">{s.active}</option>
              <option value="false">{s.disabled}</option>
            </select>
          </Field>
        </div>
        <div className="flex gap-2 mt-4">
          <button className="btn" onClick={saveDiscount} disabled={saving}>
            {saving ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
            ) : (<><Icon name="check" size={16} /><span>{dcId ? s.update : s.add}</span></>)}
          </button>
          {dcId && (
            <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={resetDiscountForm}>
              {s.cancel}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
