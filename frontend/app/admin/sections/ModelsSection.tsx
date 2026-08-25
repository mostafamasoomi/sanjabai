'use client'

import { useCallback, useEffect, useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/adminI18n'
import { SectionHeader, Field } from './shared'
import { ErrorCard, RefreshButton } from './LoadState'
import { api, errMessage } from '../api'
import { modelsSectionStrings } from './ModelsSection.strings'

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
  const lang = useLang()
  const s = modelsSectionStrings(lang)
  const f = fmt(lang)
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
      setLoadError(errMessage(err, s.loadError))
      setStatus('error')
    }
  }, [s.loadError])

  useEffect(() => { load() }, [load])

  const saveOrgDefaultModel = async () => {
    if (status !== 'ready') return
    setSaving(true)
    try {
      await api('/api/admin/org-default-model', {
        method: 'POST',
        body: JSON.stringify({ default_model: orgDefaultModel || null }),
      })
      toast(s.saveSuccess, 'success')
    } catch (err) {
      toast(errMessage(err, s.saveError), 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <SectionHeader title={s.title} subtitle={s.subtitle(f.num(models.length))} />
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
              <h3 className="text-sm font-bold text-primary">{s.cardTitle}</h3>
              <p className="text-xs text-muted">{s.cardSubtitle}</p>
            </div>
          </div>
          <Field label={s.fieldLabel}>
            <div className="flex items-center gap-3">
              <select
                className="input flex-1"
                value={orgDefaultModel}
                disabled={status !== 'ready'}
                onChange={(e) => setOrgDefaultModel(e.target.value)}
              >
                <option value="">{s.noDefaultOption}</option>
                {models.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
              <button className="btn" onClick={saveOrgDefaultModel} disabled={saving || status !== 'ready'}>
                {saving ? (
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                ) : s.save}
              </button>
            </div>
          </Field>
        </div>
      )}
    </div>
  )
}
