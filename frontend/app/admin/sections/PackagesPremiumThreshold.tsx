'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/adminI18n'
import { Field } from './shared'
import type { PackagesSectionProps } from './PackagesTypes'
import { packagesPremiumThresholdStrings } from './PackagesPremiumThreshold.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   The "expensive model" price threshold that decides which requests count
   against a package's `premium_rate_limit_per_window` (PackagesRow.tsx) --
   a model is "premium/expensive" when its input price is strictly greater
   than this many Toman per million tokens.

   Server contract (backend/admin_packages.py):
     GET  /api/admin/premium-threshold  -> { value, default, row_missing }
     POST /api/admin/premium-threshold  <- { value: number }

   Shape mirrors FreeTierSection.tsx (same load/dirty/save/cancel dance) but
   for a single value instead of three.
   ═══════════════════════════════════════════════════════════════════════════ */

interface ThresholdData {
  value: number
  default: number
  row_missing: boolean
}

export default function PackagesPremiumThreshold({ api }: PackagesSectionProps) {
  const lang = useLang()
  const s = packagesPremiumThresholdStrings(lang)
  const f = fmt(lang)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<ThresholdData | null>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api('/api/admin/premium-threshold')
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || s.serverErrorGeneric(f.num(res.status)))
      }
      const body: ThresholdData = await res.json()
      setData(body)
      setDraft(String(body.value))
    } catch (e) {
      setError(e instanceof Error && e.message !== 'unauthorized' ? e.message : s.loadError)
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [api, s, f])

  useEffect(() => { load() }, [load])

  const trimmed = draft.trim()
  const invalid = trimmed !== '' && !/^\d+$/.test(trimmed)
  const dirty = !!data && !invalid && trimmed !== '' && Number(trimmed) !== data.value

  const save = async () => {
    if (!data || !dirty || invalid) return
    setSaving(true)
    try {
      const res = await api('/api/admin/premium-threshold', {
        method: 'POST',
        body: JSON.stringify({ value: Number(trimmed) }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        toast(body.detail || s.saveErrorGeneric, 'error')
        return
      }
      toast(s.saved, 'success')
      await load()
    } catch {
      toast(s.saveErrorGeneric, 'error')
    } finally {
      setSaving(false)
    }
  }

  if (error) {
    return (
      <div className="admin-card" style={{ borderRight: '3px solid var(--danger, #ef4444)' }}>
        <div className="flex items-center gap-2 mb-2">
          <Icon name="warning" size={18} style={{ color: 'var(--danger, #ef4444)' }} />
          <h3 className="font-semibold text-sm text-primary">{s.loadFailedTitle}</h3>
        </div>
        <p className="text-xs text-muted mb-4">{error}</p>
        <button className="btn btn-sm" onClick={load}>
          <Icon name="refresh" size={14} />
          <span>{s.retry}</span>
        </button>
      </div>
    )
  }

  return (
    <div className="admin-card">
      {loading ? (
        <p className="text-sm text-muted">{s.loading}</p>
      ) : !data ? (
        <p className="text-sm text-muted">{s.noData}</p>
      ) : (
        <>
          <Field label={s.fieldLabel}>
            <div className="flex items-center gap-2">
              <input
                type="text" inputMode="numeric" className="input" dir="ltr"
                style={{ maxWidth: '12rem' }}
                value={draft} disabled={saving}
                onChange={(e) => setDraft(e.target.value)}
              />
              <span className="text-xs text-muted">{s.unit}</span>
              {data.value !== data.default && (
                <span className="text-xs text-muted">{s.defaultNote(f.num(data.default))}</span>
              )}
            </div>
          </Field>
          <p className="text-xs text-muted mt-1">
            {s.explain}
          </p>
          {invalid && (
            <p className="text-xs mt-1" style={{ color: 'var(--danger, #ef4444)' }}>
              {s.invalid}
            </p>
          )}
          <div className="flex items-center gap-3 flex-wrap mt-3">
            <button className="btn btn-sm" onClick={save} disabled={!dirty || invalid || saving}>
              {saving ? (
                <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
              ) : (
                <>
                  <Icon name="check" size={14} />
                  <span>{s.save}</span>
                </>
              )}
            </button>
            {dirty && !saving && (
              <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }}
                onClick={() => data && setDraft(String(data.value))}>
                {s.cancel}
              </button>
            )}
            {!dirty && !invalid && <span className="text-xs text-muted">{s.noChanges}</span>}
          </div>
          {data.row_missing && (
            <p className="text-xs text-muted mt-2">
              {s.rowMissing}
            </p>
          )}
        </>
      )}
    </div>
  )
}
