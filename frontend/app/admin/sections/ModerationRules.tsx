'use client'

import { useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faDate } from '@/lib/format'
import { Field } from './shared'
import { ErrorCard, RefreshButton, CardSkeleton } from './LoadState'
import { api, errMessage } from '../api'
import { useAdminResource } from '../useAdminResource'
import { SEVERITY_COLOR, SEVERITY_LABEL, SEVERITY_ORDER, type ModerationRule } from './moderationTypes'

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
  const { data: rules, error, loading, reload } = useAdminResource<ModerationRule[]>(
    '/api/admin/moderation/rules',
    (raw) => (Array.isArray(raw) ? raw : raw?.items || []),
    'خطا در دریافت قوانین پالایش',
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
      toast(form.id ? 'قانون ویرایش شد' : 'قانون اضافه شد', 'success')
      resetForm()
      reload() // refetch after mutation — a saved rule missing from the list reads as a failed save
    } catch (err) {
      const msg = errMessage(err, 'خطا در ذخیره قانون')
      setSaveError(msg) // the backend's Persian validation error, shown verbatim
      toast(msg, 'error')
    } finally {
      setSaving(false)
    }
  }

  const deleteRule = async (id: number) => {
    try {
      await api(`/api/admin/moderation/rules/${id}`, { method: 'DELETE' })
      toast('قانون حذف شد', 'success')
      if (form.id === String(id)) resetForm()
      reload()
    } catch (err) {
      toast(errMessage(err, 'خطا در حذف قانون'), 'error')
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
            <h3 className="font-semibold text-sm text-primary">قوانین پالایش</h3>
            <span className="badge badge-accent mr-auto">{list.length}</span>
            <RefreshButton onClick={reload} busy={loading} />
          </div>

          {list.length === 0 ? (
            <div className="text-center py-8 text-sm text-muted">قانونی ثبت نشده</div>
          ) : (
            <table className="admin-table w-full text-sm">
              <thead>
                <tr>
                  <th className="text-right p-3">الگو</th>
                  <th className="text-right p-3">دسته‌بندی</th>
                  <th className="text-right p-3">شدت</th>
                  <th className="text-right p-3">وضعیت</th>
                  <th className="text-right p-3">یادداشت</th>
                  <th className="text-right p-3">به‌روزرسانی</th>
                  <th className="text-right p-3">عملیات</th>
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
                        {SEVERITY_LABEL[r.severity] ?? r.severity}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className={r.enabled ? 'badge badge-positive' : 'badge badge-warning'}>{r.enabled ? 'فعال' : 'غیرفعال'}</span>
                    </td>
                    <td className="p-3 text-xs text-secondary break-words max-w-xs">{r.notes || '—'}</td>
                    <td className="p-3 text-xs text-muted">{faDate(r.updated_at)}</td>
                    <td className="p-3">
                      <div className="flex gap-1">
                        <button className="btn btn-sm" onClick={() => editRule(r)} title="ویرایش"><Icon name="settings" size={14} /></button>
                        <button className="btn btn-sm btn-danger" onClick={() => deleteRule(r.id)} title="حذف"><Icon name="trash" size={14} /></button>
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
        <h3 className="font-semibold text-sm mb-1 text-primary">{form.id ? 'ویرایش قانون' : 'افزودن قانون جدید'}</h3>
        <p className="text-xs text-muted mb-4">
          الگو (regex) باید نگارش‌های فارسی، فینگلیش و شکل‌های نویسه‌ای مختلف را پوشش دهد —
          ی/ي، ک/ك، نیم‌فاصله، و ارقام فارسی/عربی (۰۱۲... و ٠١٢...) در کنار ارقام لاتین.
        </p>
        {saveError && <ErrorCard message={saveError} onRetry={saveRule} />}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-3">
          <div className="sm:col-span-2">
            <Field label="الگوی Regex">
              <input
                className="input w-full font-mono" dir="ltr" value={form.pattern}
                onChange={(e) => setForm({ ...form, pattern: e.target.value })}
                placeholder="مثال: [هه]روئ[یي]ن|hero[iy]n"
              />
            </Field>
          </div>
          <Field label="دسته‌بندی">
            <input className="input w-full" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="مثال: مواد مخدر" />
          </Field>
          <Field label="شدت">
            <select className="input w-full" value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>
              {SEVERITY_OPTIONS.map((s) => <option key={s} value={s}>{SEVERITY_LABEL[s]}</option>)}
            </select>
          </Field>
          <Field label="وضعیت">
            <select className="input w-full" value={String(form.enabled)} onChange={(e) => setForm({ ...form, enabled: e.target.value === 'true' })}>
              <option value="true">فعال</option>
              <option value="false">غیرفعال</option>
            </select>
          </Field>
          <div className="sm:col-span-2">
            <Field label="یادداشت">
              <textarea className="input w-full" rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="توضیح دلیل یا زمینه این قانون..." />
            </Field>
          </div>
        </div>
        <div className="flex gap-2 mt-4">
          <button className="btn" onClick={saveRule} disabled={saving || !form.pattern.trim()}>
            {saving ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
            ) : (<><Icon name="check" size={16} /><span>{form.id ? 'بروزرسانی' : 'افزودن'}</span></>)}
          </button>
          {form.id && <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={resetForm}>انصراف</button>}
        </div>
      </div>
    </div>
  )
}
