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

export default function PricingSection() {
  const { data: prices, error, loading, reload, setData } = useAdminResource<PricingRow[]>(
    '/api/admin/pricing',
    (raw) => (Array.isArray(raw) ? raw : raw?.pricing || []),
    'خطا در دریافت تعرفه‌ها',
  )

  const [pzModel, setPzModel] = useState('')
  const [pzIn, setPzIn] = useState('')
  const [pzOut, setPzOut] = useState('')
  const [pzCur, setPzCur] = useState('IRT')
  const [saving, setSaving] = useState(false)

  const [togglingModel, setTogglingModel] = useState<string | null>(null)
  const [testingModel, setTestingModel] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, ModelTestResult>>({})

  const resetForm = () => { setPzModel(''); setPzIn(''); setPzOut(''); setPzCur('IRT') }

  const savePricing = async () => {
    if (!pzModel.trim()) return
    setSaving(true)
    try {
      await api('/api/admin/pricing', {
        method: 'POST',
        body: JSON.stringify({ model: pzModel, input_per_million: +pzIn || 0, output_per_million: +pzOut || 0, currency: pzCur }),
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
              {prices.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-6 text-center text-sm text-muted">
                    تعرفه‌ای ثبت نشده
                  </td>
                </tr>
              ) : (
                prices.map((p) => {
                  const testResult = testResults[p.model]
                  const isDisabled = p.availability === 'disabled'
                  return (
                    <tr key={p.model}>
                      <td className="p-3 text-sm font-mono font-medium text-primary">{p.model}</td>
                      <td className="p-3 text-xs">{faNum(p.input_per_million)}</td>
                      <td className="p-3 text-xs">{faNum(p.output_per_million)}</td>
                      <td className="p-3"><span className="badge">{p.currency}</span></td>
                      <td className="p-3">
                        <button
                          className="badge"
                          style={{
                            cursor: 'pointer',
                            background: isDisabled ? 'var(--danger-dim, #4a1a1a)' : 'var(--success-dim, #143a1e)',
                            color: isDisabled ? 'var(--danger, #e35d5d)' : 'var(--success, #4ade80)',
                          }}
                          disabled={togglingModel === p.model}
                          onClick={() => toggleModel(p.model)}
                          title="کلیک برای تغییر وضعیت"
                        >
                          {togglingModel === p.model ? '...' : (isDisabled ? 'غیرفعال' : 'فعال')}
                        </button>
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
                        <button className="btn btn-sm" onClick={() => { setPzModel(p.model); setPzIn(String(p.input_per_million)); setPzOut(String(p.output_per_million)); setPzCur(p.currency) }}>
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
          {pzModel ? `ویرایش ${pzModel}` : 'افزودن تعرفه جدید'}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Field label="نام مدل">
            <input className="input w-full" value={pzModel} onChange={(e) => setPzModel(e.target.value)} placeholder="gpt-4o" />
          </Field>
          <Field label="ورودی / میلیون توکن">
            <input className="input w-full" type="number" value={pzIn} onChange={(e) => setPzIn(e.target.value)} placeholder="0" />
          </Field>
          <Field label="خروجی / میلیون توکن">
            <input className="input w-full" type="number" value={pzOut} onChange={(e) => setPzOut(e.target.value)} placeholder="0" />
          </Field>
          <Field label="واحد پول">
            <input className="input w-full" value={pzCur} onChange={(e) => setPzCur(e.target.value)} />
          </Field>
        </div>
        <div className="flex gap-2 mt-4">
          <button className="btn" onClick={savePricing} disabled={saving}>
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
