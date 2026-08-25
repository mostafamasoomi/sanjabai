'use client'

import { useCallback, useEffect, useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum } from '@/lib/format'
import { SectionHeader, Field } from './shared'
import { ErrorCard, RefreshButton } from './LoadState'
import { api, errMessage } from '../api'

/* ═══════════════════════════════════════════════════════════════════════════
   Models — just the org default-model picker card. Self-contained; the card
   used to be driven by AdminPanel's loadAll().

   This used to also mount <ModelsTab /> (the full catalog table — search,
   bulk enable/disable, per-row upstream/pricing edit). That was a straight
   duplicate of ./ModelOpsSection.tsx's «کاتالوگ و عملیات» tab down to the
   same admin_catalog.py endpoints, plus a third copy of PricingSection's
   price editor. Deleted (see components/ModelsTab.tsx, removed) — it cost
   this tab an extra GET /api/admin/catalog/models fetch (full 1,196-row
   catalog, ~525KB, admin-only fields the picker below never needs) for a
   screen whose only job is choosing one default model from a dropdown.

   The dropdown is fed by GET /catalog/models, not the /api/models the shell
   used to call: that path has no backend route (verified — it 404s), so the
   fetch failed on every login, the catch swallowed it, and the "مدل پیشفرض
   سازمان" select was permanently empty. GET /org/default-model supplies the
   current value; POST /admin/org-default-model writes it
   (backend/content.py, backend/admin_content.py).
   ═══════════════════════════════════════════════════════════════════════════ */

export default function ModelsSection() {
  const [status, setStatus] = useState<'loading' | 'error' | 'ready'>('loading')
  const [loadError, setLoadError] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [orgDefaultModel, setOrgDefaultModel] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setStatus('loading')
    setLoadError('')
    try {
      const [catalogRes, defaultRes] = await Promise.all([
        api('/api/catalog/models'),
        api('/api/org/default-model'),
      ])
      const catalog = await catalogRes.json()
      const current = await defaultRes.json()
      setModels(((catalog?.data || []) as { id: string }[]).map((m) => m.id))
      setOrgDefaultModel(current?.default_model || '')
      setStatus('ready')
    } catch (err) {
      setLoadError(errMessage(err, 'خطا در دریافت فهرست مدل‌ها'))
      setStatus('error')
    }
  }, [])

  useEffect(() => { load() }, [load])

  const saveOrgDefaultModel = async () => {
    if (status !== 'ready') return
    setSaving(true)
    try {
      await api('/api/admin/org-default-model', {
        method: 'POST',
        body: JSON.stringify({ default_model: orgDefaultModel || null }),
      })
      toast('مدل پیشفرض سازمان ذخیره شد', 'success')
    } catch (err) {
      toast(errMessage(err, 'خطا در ذخیره مدل پیشفرض'), 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <SectionHeader title="مدل‌های فعال" subtitle={`${faNum(models.length)} مدل در دسترس`} />
        <RefreshButton onClick={load} busy={status === 'loading'} />
      </div>

      {status === 'error' && <ErrorCard message={loadError} onRetry={load} />}

      {status !== 'error' && (
        <div className="admin-card">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'var(--accent-dim)' }}>
              <Icon name="models" size={16} className="text-accent" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-primary">مدل پیشفرض سازمان</h3>
              <p className="text-xs text-muted">مدلی که کاربران جدید به‌صورت پیشفرض استفاده می‌کنند</p>
            </div>
          </div>
          <Field label="مدل">
            <div className="flex items-center gap-3">
              <select
                className="input flex-1"
                value={orgDefaultModel}
                disabled={status !== 'ready'}
                onChange={(e) => setOrgDefaultModel(e.target.value)}
              >
                <option value="">بدون مدل پیشفرض (اولین مدل لیست)</option>
                {models.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
              <button className="btn" onClick={saveOrgDefaultModel} disabled={saving || status !== 'ready'}>
                {saving ? (
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                ) : 'ذخیره'}
              </button>
            </div>
          </Field>
        </div>
      )}
    </div>
  )
}
