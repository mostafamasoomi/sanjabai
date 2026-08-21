'use client'

import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { SectionHeader, Field } from './shared'
import type { PricingRow, CreditPackageRow, ModelTestResult } from '../AdminPanel'

/* ═══════════════════════════════════════════════════════════════════════════
   Pricing — moved verbatim out of AdminPanel.tsx (page === 'pricing'):
   per-model pricing table + form, and the credit/token package table + form.
   All state and handlers still live in AdminPanel; this component is purely
   presentational.
   ═══════════════════════════════════════════════════════════════════════════ */

interface PricingSectionProps {
  prices: PricingRow[]
  testResults: Record<string, ModelTestResult>
  togglingModel: string | null
  testingModel: string | null
  toggleModel: (model: string, currentAvailability?: string) => void
  testModel: (model: string) => void
  pzModel: string
  setPzModel: (v: string) => void
  pzIn: string
  setPzIn: (v: string) => void
  pzOut: string
  setPzOut: (v: string) => void
  pzCur: string
  setPzCur: (v: string) => void
  savePricing: () => void
  creditPackages: CreditPackageRow[]
  models: string[]
  cpId: string
  setCpId: (v: string) => void
  cpNameFa: string
  setCpNameFa: (v: string) => void
  cpNameEn: string
  setCpNameEn: (v: string) => void
  cpBaseAmount: string
  setCpBaseAmount: (v: string) => void
  cpTotalCredits: string
  setCpTotalCredits: (v: string) => void
  cpBonusPercent: string
  setCpBonusPercent: (v: string) => void
  cpModelId: string
  setCpModelId: (v: string) => void
  cpSaving: boolean
  saveCreditPackage: () => void
  toggleCreditPackageActive: (pkg: CreditPackageRow) => void
}

export default function PricingSection({
  prices, testResults, togglingModel, testingModel, toggleModel, testModel,
  pzModel, setPzModel, pzIn, setPzIn, pzOut, setPzOut, pzCur, setPzCur, savePricing,
  creditPackages, models,
  cpId, setCpId, cpNameFa, setCpNameFa, cpNameEn, setCpNameEn,
  cpBaseAmount, setCpBaseAmount, cpTotalCredits, setCpTotalCredits,
  cpBonusPercent, setCpBonusPercent, cpModelId, setCpModelId, cpSaving,
  saveCreditPackage, toggleCreditPackageActive,
}: PricingSectionProps) {
  return (
    <div className="space-y-6">
      <SectionHeader title="مدیریت تعرفه‌ها" subtitle="قیمت‌گذاری مدل‌ها به ازای هر میلیون توکن" />

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
              prices.map((p: any) => {
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
                        onClick={() => toggleModel(p.model, p.availability)}
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
          <button className="btn" onClick={savePricing}>
            <Icon name="check" size={16} />
            <span>ذخیره</span>
          </button>
          {pzModel && (
            <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={() => { setPzModel(''); setPzIn(''); setPzOut(''); setPzCur('IRT') }}>
              انصراف
            </button>
          )}
        </div>
      </div>

      {/* Token / Credit Packages — "N million tokens of <model> for <price>" bundles */}
      <SectionHeader title="بسته‌های اعتباری / توکن" subtitle="بسته‌هایی که در کیف پول کاربران قابل خریدند — با برچسب مدل، به‌صورت «N میلیون توکن مدل X» نمایش داده می‌شوند" />

      <div className="admin-card overflow-x-auto">
        <table className="admin-table w-full text-sm">
          <thead>
            <tr>
              <th className="text-right p-3">شناسه</th>
              <th className="text-right p-3">نام</th>
              <th className="text-right p-3">مدل</th>
              <th className="text-right p-3">مبلغ (تومان)</th>
              <th className="text-right p-3">وضعیت</th>
              <th className="text-right p-3">عملیات</th>
            </tr>
          </thead>
          <tbody>
            {creditPackages.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-6 text-center text-sm text-muted">
                  بسته‌ای ثبت نشده — از فرم پایین برای افزودن یک بسته استفاده کنید
                </td>
              </tr>
            ) : (
              creditPackages.map((pkg) => (
                <tr key={pkg.id}>
                  <td className="p-3 text-sm font-mono text-primary">{pkg.id}</td>
                  <td className="p-3 text-sm">{pkg.name_fa}</td>
                  <td className="p-3 text-xs font-mono">{pkg.model_id || '—'}</td>
                  <td className="p-3 text-xs">{faNum(pkg.base_amount)}</td>
                  <td className="p-3">
                    <button
                      className="badge"
                      style={{
                        cursor: 'pointer',
                        background: pkg.active ? 'var(--success-dim, #143a1e)' : 'var(--danger-dim, #4a1a1a)',
                        color: pkg.active ? 'var(--success, #4ade80)' : 'var(--danger, #e35d5d)',
                      }}
                      onClick={() => toggleCreditPackageActive(pkg)}
                    >
                      {pkg.active ? 'فعال' : 'غیرفعال'}
                    </button>
                  </td>
                  <td className="p-3">
                    <button
                      className="btn btn-sm"
                      onClick={() => {
                        setCpId(pkg.id); setCpNameFa(pkg.name_fa); setCpNameEn(pkg.name_en)
                        setCpBaseAmount(String(pkg.base_amount)); setCpTotalCredits(String(pkg.total_credits))
                        setCpBonusPercent(String(pkg.bonus_percent)); setCpModelId(pkg.model_id || '')
                      }}
                    >
                      <Icon name="settings" size={14} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="admin-card">
        <h3 className="font-semibold text-sm mb-4 text-primary">
          {cpId ? `ویرایش بسته ${cpId}` : 'افزودن بسته جدید'}
        </h3>
        <p className="text-xs text-muted mb-4">
          «مبلغ پرداختی» همان چیزی است که واقعاً از کاربر گرفته می‌شود؛ «اعتبار دریافتی» چیزی است که به کیف پول اضافه می‌شود — اگر اعتبار دریافتی بیشتر از مبلغ پرداختی باشد، تفاوت همان بونوس واقعی است. هر دو به ریال هستند. مدل انتخابی صرفاً برچسب است؛ اعتبار در کیف پول عمومی کاربر شارژ می‌شود و طبق قیمت زنده هر مدل مصرف می‌شود.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <Field label="شناسه بسته (یکتا)">
            <input className="input w-full" value={cpId} onChange={(e) => setCpId(e.target.value)} placeholder="pkg_mimo_20m" disabled={!!cpId && creditPackages.some((p) => p.id === cpId)} />
          </Field>
          <Field label="نام فارسی">
            <input className="input w-full" value={cpNameFa} onChange={(e) => setCpNameFa(e.target.value)} placeholder="۲۰ میلیون توکن mimo" />
          </Field>
          <Field label="نام انگلیسی">
            <input className="input w-full" value={cpNameEn} onChange={(e) => setCpNameEn(e.target.value)} placeholder="20M mimo tokens" />
          </Field>
          <Field label="مدل مرتبط (اختیاری)">
            <select className="input w-full" value={cpModelId} onChange={(e) => setCpModelId(e.target.value)} style={{ appearance: 'auto' }}>
              <option value="">— بدون مدل (اعتبار عمومی) —</option>
              {models.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </Field>
          <Field label="مبلغ پرداختی (ریال)">
            <input className="input w-full" type="number" value={cpBaseAmount} onChange={(e) => setCpBaseAmount(e.target.value)} placeholder="200000" />
          </Field>
          <Field label="اعتبار دریافتی (ریال)">
            <input className="input w-full" type="number" value={cpTotalCredits} onChange={(e) => setCpTotalCredits(e.target.value)} placeholder="200000" />
          </Field>
        </div>
        <div className="flex gap-2 mt-4">
          <button className="btn" onClick={saveCreditPackage} disabled={cpSaving}>
            {cpSaving ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
            ) : (<><Icon name="check" size={16} /><span>ذخیره</span></>)}
          </button>
          {cpId && (
            <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={() => { setCpId(''); setCpNameFa(''); setCpNameEn(''); setCpBaseAmount(''); setCpTotalCredits(''); setCpBonusPercent('0'); setCpModelId('') }}>
              انصراف
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
