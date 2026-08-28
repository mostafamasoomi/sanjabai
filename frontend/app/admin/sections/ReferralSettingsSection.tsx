'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { SectionHeader, Field } from './shared'
import { referralSettingsSectionStrings } from './ReferralSettingsSection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Referral settings -- new sub-tab of the products module (productsTabs.ts:
   'referral'), not a new AdminPanel nav entry.

   Server contract (F-REF, phase 5 -- built in parallel by the backend agent;
   this file is written against the pinned shape and must not crash if the
   route does not exist yet):

     GET  /admin/referral/settings
       -> { referral_reward_toman, referral_invitee_reward_toman,
            referral_reward_cap,
            stats: { pending, paid, capped, total_paid_toman } }
     PUT  /admin/referral/settings   <- the same three top-level numbers

   Reached through the frontend as /api/admin/referral/settings -- next.config.js
   rewrites /api/:path* to the backend with the /api prefix stripped.

   Load/dirty/save/cancel shape copied from FreeTierSection.tsx (three
   numeric fields, per-field dirty diff, one save call). The one addition
   is the "not built yet" state below.

   ── The 404-vs-real-error distinction ─────────────────────────────────────
   `api()` (../api.ts) throws on any non-2xx, so by the time an exception
   reaches this component's catch block the HTTP status is gone -- only the
   message survives, built by apiError.ts's errorDetail() from the response
   body's `detail`. Curl-verified against this exact route (2026-08-28,
   before the backend agent had added it):

       $ curl -si http://127.0.0.1:8001/admin/referral/settings
       HTTP/1.1 404 Not Found
       {"detail":"Not Found"}

   That is Starlette's own unmatched-route body, not anything this endpoint
   could ever emit once it exists (a real "not found" here would be a
   config row, and GET builds one on the fly from defaults -- see
   PackagesPremiumThreshold.tsx's `row_missing` for the analogous case, which
   answers 200 with a flag rather than 404). So `message === 'Not Found'` is
   read as "route not registered yet", not as a generic error, and shown as
   a calm bilingual "not live yet" panel instead of the scary red error card.
   ═══════════════════════════════════════════════════════════════════════════ */

interface ReferralStats {
  pending: number
  paid: number
  capped: number
  total_paid_toman: number
}

interface ReferralData {
  referral_reward_toman: number
  referral_invitee_reward_toman: number
  referral_reward_cap: number
  stats: ReferralStats
}

type FieldKey = 'referral_reward_toman' | 'referral_invitee_reward_toman' | 'referral_reward_cap'

interface ReferralSettingsSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

const ENDPOINT = '/api/admin/referral/settings'

export default function ReferralSettingsSection({ api }: ReferralSettingsSectionProps) {
  const lang = useLang()
  const s = referralSettingsSectionStrings(lang)
  const f = fmt(lang)

  const FIELDS: { key: FieldKey; label: string; help: string; unit: string }[] = [
    { key: 'referral_reward_toman', label: s.referrerRewardLabel, help: s.referrerRewardHelp, unit: s.unitToman },
    { key: 'referral_invitee_reward_toman', label: s.inviteeRewardLabel, help: s.inviteeRewardHelp, unit: s.unitToman },
    { key: 'referral_reward_cap', label: s.capLabel, help: s.capHelp, unit: s.unitCount },
  ]

  const [loading, setLoading] = useState(true)
  const [notBuilt, setNotBuilt] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<ReferralData | null>(null)
  const [saving, setSaving] = useState(false)
  const [draft, setDraft] = useState<Record<FieldKey, string>>({
    referral_reward_toman: '',
    referral_invitee_reward_toman: '',
    referral_reward_cap: '',
  })

  const applyData = (body: ReferralData) => {
    setData(body)
    setDraft({
      referral_reward_toman: String(body.referral_reward_toman),
      referral_invitee_reward_toman: String(body.referral_invitee_reward_toman),
      referral_reward_cap: String(body.referral_reward_cap),
    })
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setNotBuilt(false)
    try {
      const res = await api(ENDPOINT)
      if (!res.ok) {
        if (res.status === 404) { setNotBuilt(true); setData(null); return }
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || s.serverError(String(res.status)))
      }
      const body: ReferralData = await res.json()
      applyData(body)
    } catch (e) {
      // See the header comment: a thrown 'Not Found' is the same
      // route-not-registered signal as an inline 404 above, just arriving
      // through api()'s own throw-on-non-2xx instead of a returned Response.
      if (e instanceof Error && e.message === 'Not Found') { setNotBuilt(true); setData(null); return }
      setError(e instanceof Error && e.message !== 'unauthorized' ? e.message : s.loadError)
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [api, s])

  useEffect(() => { load() }, [load])

  const changed: Partial<Record<FieldKey, number>> = {}
  if (data) {
    for (const field of FIELDS) {
      const raw = draft[field.key].trim()
      if (raw === '' || !/^\d+$/.test(raw)) continue
      const n = parseInt(raw, 10)
      if (n !== data[field.key]) changed[field.key] = n
    }
  }
  const dirty = Object.keys(changed).length > 0

  const invalidField = data
    ? FIELDS.find((field) => { const r = draft[field.key].trim(); return r !== '' && !/^\d+$/.test(r) })
    : undefined

  const save = async () => {
    if (!data || !dirty || invalidField) return
    setSaving(true)
    try {
      const res = await api(ENDPOINT, { method: 'PUT', body: JSON.stringify(changed) })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        toast(body.detail || s.saveErrorGeneric, 'error')
        return
      }
      toast(s.saved, 'success')
      await load()
    } catch (e) {
      toast(e instanceof Error && e.message !== 'unauthorized' ? e.message : s.saveErrorGeneric, 'error')
    } finally {
      setSaving(false)
    }
  }

  if (notBuilt) {
    return (
      <div className="space-y-6">
        <SectionHeader title={s.title} subtitle={s.subtitle} />
        <div className="admin-card" style={{ borderRight: '3px solid var(--text-muted)' }}>
          <div className="flex items-center gap-2 mb-2">
            <Icon name="info" size={18} style={{ color: 'var(--text-muted)' }} />
            <h3 className="font-semibold text-sm text-primary">{s.notBuiltTitle}</h3>
          </div>
          <p className="text-xs text-muted mb-4">{s.notBuiltBody}</p>
          <button className="btn btn-sm" onClick={load}>
            <Icon name="refresh" size={14} />
            <span>{s.retry}</span>
          </button>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-6">
        <SectionHeader title={s.title} subtitle={s.subtitle} />
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
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <SectionHeader title={s.title} subtitle={s.subtitle} />

      {loading ? (
        <div className="admin-card p-6 text-center text-sm text-muted">{s.loading}</div>
      ) : !data ? (
        <div className="admin-card p-6 text-center text-sm text-muted">{s.noData}</div>
      ) : (
        <>
          <div className="admin-card space-y-4">
            {FIELDS.map((field) => (
              <Field key={field.key} label={field.label}>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    inputMode="numeric"
                    className="input"
                    dir="ltr"
                    style={{ maxWidth: '12rem' }}
                    value={draft[field.key]}
                    disabled={saving}
                    onChange={(e) => setDraft((prev) => ({ ...prev, [field.key]: e.target.value }))}
                  />
                  <span className="text-xs text-muted">{field.unit}</span>
                </div>
                <p className="text-xs text-muted mt-1">{field.help}</p>
              </Field>
            ))}

            {invalidField && (
              <p className="text-xs" style={{ color: 'var(--danger, #ef4444)' }}>
                {s.invalidField(invalidField.label)}
              </p>
            )}

            <p className="text-xs text-muted">{s.zeroNote}</p>
            <p className="text-xs text-muted">{s.payoutNote}</p>

            <div className="flex items-center gap-3 flex-wrap">
              <button className="btn btn-sm" onClick={save} disabled={!dirty || !!invalidField || saving}>
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
                <button
                  className="btn btn-sm"
                  style={{ background: 'var(--bg-elevated)' }}
                  onClick={() => applyData(data)}
                >
                  {s.cancel}
                </button>
              )}
              {!dirty && !invalidField && <span className="text-xs text-muted">{s.noChanges}</span>}
            </div>
          </div>

          <div className="admin-card">
            <h3 className="font-semibold text-sm text-primary mb-3">{s.statsTitle}</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div>
                <p className="text-xs text-muted">{s.statPending}</p>
                <p className="text-lg font-bold text-primary">{f.num(data.stats.pending)}</p>
              </div>
              <div>
                <p className="text-xs text-muted">{s.statPaid}</p>
                <p className="text-lg font-bold text-primary">{f.num(data.stats.paid)}</p>
              </div>
              <div>
                <p className="text-xs text-muted">{s.statCapped}</p>
                <p className="text-lg font-bold text-primary">{f.num(data.stats.capped)}</p>
              </div>
              <div>
                <p className="text-xs text-muted">{s.statTotalPaid}</p>
                <p className="text-lg font-bold text-primary">{f.price(data.stats.total_paid_toman)}</p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
