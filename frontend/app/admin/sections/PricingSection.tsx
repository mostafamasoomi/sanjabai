'use client'

import { useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum } from '@/lib/format'
import { SectionHeader, Field } from './shared'
import { ErrorCard, RefreshButton, CardSkeleton } from './LoadState'
import { api, errMessage } from '../api'
import { useAdminResource } from '../useAdminResource'
import type { PricingRow, ModelTestResult } from '../types'

/* ═══════════════════════════════════════════════════════════════════════════
   Pricing — per-model tariffs: GET/POST /admin/pricing, plus the per-model
   availability toggle and live probe (backend/admin_pricing.py).

   The credit/token package table and form that used to sit at the bottom of
   this screen are GONE. They wrote to POST /admin/credit-packages
   (backend/admin_plans.py), which hardcodes `active: true` and skips the
   loss-path validation that POST /admin/packages runs — two admin screens
   writing the same table, one of them able to publish a package that sells
   at a loss. بسته‌ها (PackagesSection) is now the only writer.
   ═══════════════════════════════════════════════════════════════════════════ */

// Every state model_catalog.availability actually takes (admin_catalog.py's
// _VALID_AVAILABILITY). Labels/classes match ModelsTab.tsx's own
// AVAILABILITY_FA/AVAILABILITY_BADGE so a model reads the same status here
// as it does there.
const AVAILABILITY_FA: Record<string, string> = {
  available: 'فعال', degraded: 'کاهش‌یافته', maintenance: 'تعمیرات', disabled: 'غیرفعال',
}
const AVAILABILITY_BADGE: Record<string, string> = {
  available: 'badge-positive', degraded: 'badge-warning', maintenance: 'badge-accent', disabled: 'badge-danger',
}
// POST /admin/models/{id}/toggle (admin_pricing.py) only flips between
// these two -- it 400s on anything else. Rendering it as a clickable toggle
// on a 'maintenance'/'degraded' row used to look identical to a real
// available/disabled row and, on a free upstream, would silently put an
// unprobed model up for sale on one misclick.
const TOGGLEABLE = new Set(['available', 'disabled'])

/** Never show a raw currency code -- every other screen that renders this
 *  same model_catalog.currency column (onboardingHelpers.ts, pricing/page.tsx)
 *  translates IRT/IRR to Persian before display; this was the one place that
 *  didn't. */
function faCurrency(code: string): string {
  return code === 'IRT' ? 'تومان' : code === 'IRR' ? 'ریال' : code
}

export default function PricingSection() {
  const { data: prices, error, loading, reload, setData } = useAdminResource<PricingRow[]>(
    '/api/admin/pricing',
    (raw) => (Array.isArray(raw) ? raw : raw?.pricing || []),
    'خطا در دریافت تعرفه‌ها',
  )

  const [search, setSearch] = useState('')

  const [pzModel, setPzModel] = useState('')
  const [pzIn, setPzIn] = useState('')
  const [pzOut, setPzOut] = useState('')
  const [saving, setSaving] = useState(false)

  const [togglingModel, setTogglingModel] = useState<string | null>(null)
  const [testingModel, setTestingModel] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, ModelTestResult>>({})

  const resetForm = () => { setPzModel(''); setPzIn(''); setPzOut('') }

  // POST /admin/pricing only UPDATEs an existing model_catalog row (see
  // admin_pricing.py's set_pricing -- it 404s when rowcount is 0); it never
  // INSERTs. New catalog rows come only from model_discovery.py. So this
  // form can only ever edit a model already in `prices`, never "add" one --
  // enforced here instead of round-tripping to the 404 the backend already
  // returns.
  const knownModel = !!prices?.some((p) => p.model === pzModel.trim())

  const savePricing = async () => {
    if (!knownModel) return
    setSaving(true)
    try {
      await api('/api/admin/pricing', {
        method: 'POST',
        body: JSON.stringify({ model: pzModel.trim(), input_per_million: +pzIn || 0, output_per_million: +pzOut || 0, currency: 'IRT' }),
      })
      toast('تعرفه ذخیره شد', 'success')
      resetForm()
      reload()
    } catch (err) {
      toast(errMessage(err, 'خطا در ذخیره تعرفه'), 'error')
    } finally {
      setSaving(false)
    }
  }

  const toggleModel = async (model: string) => {
    setTogglingModel(model)
    try {
      const r = await api(`/api/admin/models/${encodeURIComponent(model)}/toggle`, { method: 'POST' })
      const data = await r.json()
      toast(data.availability === 'available' ? `${model} فعال شد` : `${model} غیرفعال شد`, 'success')
      setData((prev) => (prev || []).map((p) => (p.model === model ? { ...p, availability: data.availability } : p)))
    } catch (err) {
      toast(errMessage(err, 'خطا در تغییر وضعیت مدل'), 'error')
    } finally {
      setTogglingModel(null)
    }
  }

  const testModel = async (model: string) => {
    setTestingModel(model)
    try {
      const r = await api(`/api/admin/models/${encodeURIComponent(model)}/test`, { method: 'POST' })
      const data: ModelTestResult = await r.json()
      setTestResults((prev) => ({ ...prev, [model]: data }))
      toast(
        data.ok ? `${model} پاسخ داد (${faNum(data.latency_ms)}ms)` : `${model} پاسخ نداد: ${data.error || 'نامشخص'}`,
        data.ok ? 'success' : 'error',
      )
    } catch (err) {
      toast(errMessage(err, 'خطا در تست مدل'), 'error')
    } finally {
      setTestingModel(null)
    }
  }

  // Client-side only -- the catalog is ~1,200 rows in one GET (same as
  // ModelOpsSection's own read of this table) and there was previously no
  // way to find one model among them short of scrolling the whole table.
  const q = search.trim().toLowerCase()
  const filtered = (prices || []).filter((p) => {
    if (!q) return true
    const displayName = String((p as { display_name?: string }).display_name || '')
    return p.model.toLowerCase().includes(q) || displayName.toLowerCase().includes(q)
  })

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <SectionHeader title="مدیریت تعرفه‌ها" subtitle="قیمت‌گذاری مدل‌ها به ازای هر میلیون توکن" />
        <RefreshButton onClick={reload} busy={loading} />
      </div>

      {error && <ErrorCard message={error} onRetry={reload} />}
      {!error && !prices && <CardSkeleton count={3} />}

      {prices && (
        <div className="admin-card overflow-x-auto">
          <div className="flex items-center gap-2 p-3">
            <input
              className="input w-full sm:w-72"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="جستجوی مدل…"
            />
            <span className="text-xs text-muted">
              {faNum(filtered.length)} از {faNum(prices.length)} مدل
            </span>
          </div>
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="text-right p-3">مدل</th>
                <th className="text-right p-3">ورودی</th>
                <th className="text-right p-3">خروجی</th>
                <th className="text-right p-3">واحد</th>
                <th className="text-right p-3">وضعیت</th>
                <th className="text-right p-3">تست</th>
                <th className="text-right p-3">عملیات</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-6 text-center text-sm text-muted">
                    {prices.length === 0 ? 'تعرفه‌ای ثبت نشده' : 'موردی با این جستجو یافت نشد'}
                  </td>
                </tr>
              ) : (
                filtered.map((p) => {
                  const testResult = testResults[p.model]
                  const avail = p.availability || 'maintenance'
                  const badgeClass = `badge ${AVAILABILITY_BADGE[avail] || 'badge-accent'}`
                  const badgeLabel = AVAILABILITY_FA[avail] || avail
                  return (
                    <tr key={p.model}>
                      <td className="p-3 text-sm font-mono font-medium text-primary">{p.model}</td>
                      <td className="p-3 text-xs">{faNum(p.input_per_million)}</td>
                      <td className="p-3 text-xs">{faNum(p.output_per_million)}</td>
                      <td className="p-3"><span className="badge">{faCurrency(p.currency)}</span></td>
                      <td className="p-3">
                        {TOGGLEABLE.has(avail) ? (
                          <button
                            className={badgeClass}
                            style={{ cursor: 'pointer' }}
                            disabled={togglingModel === p.model}
                            onClick={() => toggleModel(p.model)}
                            title="کلیک برای تغییر وضعیت"
                          >
                            {togglingModel === p.model ? '...' : badgeLabel}
                          </button>
                        ) : (
                          <span className={badgeClass} title="برای تغییر وضعیت این مدل از تب «عملیات کاتالوگ» استفاده کنید">
                            {badgeLabel}
                          </span>
                        )}
                      </td>
                      <td className="p-3">
                        <button className="btn btn-sm" disabled={testingModel === p.model} onClick={() => testModel(p.model)}>
                          {testingModel === p.model ? (
                            <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                          ) : 'تست'}
                        </button>
                        {testResult && (
                          <span className="text-xs mr-2" style={{ color: testResult.ok ? 'var(--success, #4ade80)' : 'var(--danger, #e35d5d)' }}>
                            {testResult.ok ? `${faNum(testResult.latency_ms)}ms` : (testResult.error || 'خطا')}
                          </span>
                        )}
                      </td>
                      <td className="p-3">
                        <button className="btn btn-sm" onClick={() => { setPzModel(p.model); setPzIn(String(p.input_per_million)); setPzOut(String(p.output_per_million)) }}>
                          <Icon name="settings" size={14} />
                        </button>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="admin-card">
        <h3 className="font-semibold text-sm mb-4 text-primary">
          {pzModel ? `ویرایش ${pzModel}` : 'ویرایش تعرفه یک مدل موجود'}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Field label="نام مدل">
            <input
              className="input w-full"
              list="pricing-model-options"
              value={pzModel}
              onChange={(e) => setPzModel(e.target.value)}
              placeholder="جستجوی مدل موجود در کاتالوگ…"
            />
            <datalist id="pricing-model-options">
              {(prices || []).map((p) => <option key={p.model} value={p.model} />)}
            </datalist>
          </Field>
          <Field label="ورودی / میلیون توکن">
            <input className="input w-full" type="number" value={pzIn} onChange={(e) => setPzIn(e.target.value)} placeholder="0" />
          </Field>
          <Field label="خروجی / میلیون توکن">
            <input className="input w-full" type="number" value={pzOut} onChange={(e) => setPzOut(e.target.value)} placeholder="0" />
          </Field>
          <Field label="واحد پول">
            <input className="input w-full" value="تومان" disabled />
          </Field>
        </div>
        {pzModel.trim() && !knownModel && (
          <p className="text-xs mt-2" style={{ color: 'var(--danger, #e35d5d)' }}>
            این مدل هنوز در کاتالوگ نیست. این فرم فقط قیمت مدل‌های موجود را ویرایش می‌کند؛ مدل تازه فقط از
            فرآیند شناسایی خودکار وارد کاتالوگ می‌شود.
          </p>
        )}
        <div className="flex gap-2 mt-4">
          <button className="btn" onClick={savePricing} disabled={saving || !knownModel}>
            {saving ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
            ) : (<><Icon name="check" size={16} /><span>ذخیره</span></>)}
          </button>
          {pzModel && (
            <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={resetForm}>
              انصراف
            </button>
          )}
        </div>
      </div>

      <p className="text-xs text-muted">
        برای ساخت و ویرایش بسته‌های اعتباری از صفحه «بسته‌ها» استفاده کنید؛ تنها آن صفحه پیش از انتشار، ضررده نبودن بسته را بررسی می‌کند.
      </p>
    </div>
  )
}
