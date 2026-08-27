'use client'

import { useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { Field } from './shared'
import { ErrorCard, RefreshButton, CardSkeleton } from './LoadState'
import { api, errMessage } from '../api'
import { useAdminResource } from '../useAdminResource'
import { SEVERITY_COLOR, SEVERITY_ORDER, severityLabel, type ModerationRule } from './moderationTypes'
import { moderationRulesStrings } from './ModerationRules.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Moderation rule editor — list/create/edit/delete regex rules.
   GET /admin/moderation/rules ; POST create ; POST /{id} update ;
   DELETE /admin/moderation/rules/{id} (backend/admin_moderation.py).

   Persian-first: the pattern field is what actually catches a banned
   search, and Persian text has more surface area than Latin — ی/ي, ک/ك,
   نیم‌فاصله, and Persian vs. Arabic digit forms are all distinct codepoints
   that a naive pattern misses. The help text says so; it is not decorative.

   A rejected pattern is shown inline next to the field being edited (not
   just toasted) because a toast disappears before the admin has finished
   reading a regex error, and the field they need to fix is right here.
   ═══════════════════════════════════════════════════════════════════════════ */

const SEVERITY_OPTIONS = SEVERITY_ORDER

const emptyForm = { id: '', pattern: '', category: '', severity: 'medium', enabled: true, notes: '' }

export default function ModerationRules() {
  const lang = useLang()
  const s = moderationRulesStrings(lang)
  const f = fmt(lang)
  const { data: rules, error, loading, reload } = useAdminResource<ModerationRule[]>(
    '/api/admin/moderation/rules',
    (raw) => (Array.isArray(raw) ? raw : raw?.items || []),
    s.loadError,
  )

  const [form, setForm] = useState(emptyForm)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const resetForm = () => { setForm(emptyForm); setSaveError(null) }

  const editRule = (r: ModerationRule) => {
    setForm({ id: String(r.id), pattern: r.pattern, category: r.category || '', severity: r.severity, enabled: r.enabled, notes: r.notes || '' })
    setSaveError(null)
  }

  const saveRule = async () => {
    if (!form.pattern.trim()) return
    setSaving(true)
    setSaveError(null)
    try {
      const body = JSON.stringify({
        pattern: form.pattern.trim(), category: form.category.trim(), severity: form.severity,
        enabled: form.enabled, notes: form.notes.trim(),
      })
      await api(form.id ? `/api/admin/moderation/rules/${form.id}` : '/api/admin/moderation/rules', { method: 'POST', body })
      toast(form.id ? s.savedEdit : s.savedNew, 'success')
      resetForm()
      reload() // refetch after mutation — a saved rule missing from the list reads as a failed save
    } catch (err) {
      const msg = errMessage(err, s.saveErrorGeneric)
      setSaveError(msg) // the backend's own validation error, shown verbatim
      toast(msg, 'error')
    } finally {
      setSaving(false)
    }
  }

  const deleteRule = async (id: number) => {
    try {
      await api(`/api/admin/moderation/rules/${id}`, { method: 'DELETE' })
      toast(s.deleted, 'success')
      if (form.id === String(id)) resetForm()
      reload()
    } catch (err) {
      toast(errMessage(err, s.deleteErrorGeneric), 'error')
    }
  }

  const list = rules || []

  return (
    <div className="space-y-6">
      {error && <ErrorCard message={error} onRetry={reload} />}
      {!error && !rules && <CardSkeleton count={3} />}

      {rules && (
        <div className="admin-card overflow-x-auto">
          <div className="flex items-center gap-2 mb-4">
            <Icon name="security" size={18} className="text-accent" />
            <h3 className="font-semibold text-sm text-primary">{s.rulesTitle}</h3>
            <span className="badge badge-accent mr-auto">{f.num(list.length)}</span>
            <RefreshButton onClick={reload} busy={loading} />
          </div>

          {list.length === 0 ? (
            <div className="text-center py-8 text-sm text-muted">{s.noRules}</div>
          ) : (
            <table className="admin-table w-full text-sm">
              <thead>
                <tr>
                  <th className="p-3">{s.colPattern}</th>
                  <th className="p-3">{s.colCategory}</th>
                  <th className="p-3">{s.colSeverity}</th>
                  <th className="p-3">{s.colStatus}</th>
                  <th className="p-3">{s.colNotes}</th>
                  <th className="p-3">{s.colUpdated}</th>
                  <th className="p-3">{s.colActions}</th>
                </tr>
              </thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.id}>
                    <td className="p-3 text-xs font-mono break-all max-w-xs" dir="ltr">{r.pattern}</td>
                    <td className="p-3 text-xs text-secondary">{r.category || '—'}</td>
                    <td className="p-3">
                      <span
                        className="badge"
                        style={{ background: `${SEVERITY_COLOR[r.severity] ?? '#666'}20`, color: SEVERITY_COLOR[r.severity] ?? 'var(--text-secondary)' }}
                      >
                        {severityLabel(r.severity, lang)}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className={r.enabled ? 'badge badge-positive' : 'badge badge-warning'}>{r.enabled ? s.enabled : s.disabled}</span>
                    </td>
                    <td className="p-3 text-xs text-secondary break-words max-w-xs">{r.notes || '—'}</td>
                    <td className="p-3 text-xs text-muted">{f.date(r.updated_at)}</td>
                    <td className="p-3">
                      <div className="flex gap-1">
                        <button className="btn btn-sm" onClick={() => editRule(r)} title={s.edit}><Icon name="settings" size={14} /></button>
                        <button className="btn btn-sm btn-danger" onClick={() => deleteRule(r.id)} title={s.delete}><Icon name="trash" size={14} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <div className="admin-card">
        <h3 className="font-semibold text-sm mb-1 text-primary">{form.id ? s.editTitle : s.addTitle}</h3>
        <p className="text-xs text-muted mb-4">
          {s.formHelp}
        </p>
        {saveError && <ErrorCard message={saveError} onRetry={saveRule} />}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-3">
          <div className="sm:col-span-2">
            <Field label={s.patternLabel}>
              <input
                className="input w-full font-mono" dir="ltr" value={form.pattern}
                onChange={(e) => setForm({ ...form, pattern: e.target.value })}
                placeholder={s.patternPlaceholder}
              />
            </Field>
          </div>
          <Field label={s.categoryLabel}>
            <input className="input w-full" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder={s.categoryPlaceholder} />
          </Field>
          <Field label={s.severityLabel}>
            <select className="input w-full" value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>
              {SEVERITY_OPTIONS.map((sv) => <option key={sv} value={sv}>{severityLabel(sv, lang)}</option>)}
            </select>
          </Field>
          <Field label={s.statusLabel}>
            <select className="input w-full" value={String(form.enabled)} onChange={(e) => setForm({ ...form, enabled: e.target.value === 'true' })}>
              <option value="true">{s.enabled}</option>
              <option value="false">{s.disabled}</option>
            </select>
          </Field>
          <div className="sm:col-span-2">
            <Field label={s.notesLabel}>
              <textarea className="input w-full" rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder={s.notesPlaceholder} />
            </Field>
          </div>
        </div>
        <div className="flex gap-2 mt-4">
          <button className="btn" onClick={saveRule} disabled={saving || !form.pattern.trim()}>
            {saving ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
            ) : (<><Icon name="check" size={16} /><span>{form.id ? s.update : s.add}</span></>)}
          </button>
          {form.id && <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={resetForm}>{s.cancel}</button>}
        </div>
      </div>
    </div>
  )
}
