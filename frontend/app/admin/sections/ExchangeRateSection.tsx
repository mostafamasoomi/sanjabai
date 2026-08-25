'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/adminI18n'
import { SectionHeader, StatCard, Field, NumInput } from './shared'
import { exchangeRateSectionStrings } from './ExchangeRateSection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   نرخ ارز — نمایش نرخ زندهٔ دلار به تومان، منبع تأمین آن، زمان آخرین
   به‌روزرسانی، مارک‌آپ ثابت قابل‌ویرایش، و فهرست منابعی که نرخ از آن‌ها
   واکشی می‌شود (Bonbast.com در کنار tgju، به‌علاوهٔ امکان افزودن مرجع دیگر
   توسط ادمین — درخواست مالک، ۳ شهریور ۱۴۰۵ / 2026-08-25).

   Self-contained (fetches via the `api` helper AdminPanel already exposes),
   same pattern as ./MarkupSection.tsx.

   Server contract (backend/exchange_rate_admin.py):
     GET  /api/admin/exchange-rate                    -> rate meta (unchanged shape)
     POST /api/admin/exchange-rate/refresh             -> same shape, forces a fresh resolve
     GET  /api/admin/exchange-rate/flat-markup         -> { flat_markup_toman, default_toman }
     POST /api/admin/exchange-rate/flat-markup         <- { flat_markup_toman }
     GET  /api/admin/exchange-rate/sources             -> { builtin: [...], configured: [...] }
     POST /api/admin/exchange-rate/sources             <- { source_key, display_name, url, unit,
                                                              extract_regex, priority, timeout_s }
     PATCH  /api/admin/exchange-rate/sources/{key}     <- any of { enabled, priority, timeout_s,
                                                              url, extract_regex, unit }
     DELETE /api/admin/exchange-rate/sources/{key}     -- only a non-builtin (admin-added) row

   `source` mirrors backend/content.py's resolver: 'db_override' > 'tgju' >
   an enabled row from `configured` (by priority; Bonbast is seeded as
   'bonbast') > 'er_api' > 'hardcoded_fallback', plus 'unknown' for a cache
   entry written before this feature existed (a stale/unhealthy state, not
   a normal tier -- rendered distinctly on purpose, see SOURCE_META below).
   All money here is raw Toman straight from the server -- never multiplied
   or divided.
   ═══════════════════════════════════════════════════════════════════════════ */

interface ExchangeRateMeta {
  rate_irt_bare: number
  flat_markup_irt: number
  rate_irt_effective: number
  markup_pct: number
  source: string
  fetched_at: string | null
  cache_ttl_remaining_s: number | null
}

interface BuiltinSourceInfo {
  source_key: string
  display_name: string
  kind: string
  editable: boolean
  note: string
}

interface ConfiguredSource {
  source_key: string
  display_name: string
  kind: string
  url: string | null
  unit: string
  extract_regex: string | null
  enabled: boolean
  priority: number
  timeout_s: number
  is_builtin: boolean
  editable: boolean
  deletable: boolean
  updated_at: string | null
}

interface ExchangeRateSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

/** Built from the resolved strings rather than a module-level Persian
 *  literal map, so the label follows the language. `source` (the enum key)
 *  itself is data from the backend and stays untranslated. */
function sourceMetaTable(s: ReturnType<typeof exchangeRateSectionStrings>): Record<string, { label: string; color: string; healthy: boolean }> {
  return {
    db_override: { label: s.sourceDbOverride, color: 'var(--accent, #6366f1)', healthy: true },
    tgju: { label: s.sourceTgju, color: 'var(--success, #22c55e)', healthy: true },
    bonbast: { label: s.sourceBonbast, color: 'var(--success, #22c55e)', healthy: true },
    er_api: { label: s.sourceErApi, color: 'var(--warning, #eab308)', healthy: true },
    hardcoded_fallback: { label: s.sourceHardcodedFallback, color: 'var(--danger, #ef4444)', healthy: false },
    unknown: { label: s.sourceUnknown, color: 'var(--danger, #ef4444)', healthy: false },
  }
}

function sourceMeta(source: string, configured: ConfiguredSource[], s: ReturnType<typeof exchangeRateSectionStrings>) {
  const table = sourceMetaTable(s)
  if (table[source]) return table[source]
  const row = configured.find((c) => c.source_key === source)
  if (row) return { label: s.sourceCustom(row.display_name), color: 'var(--success, #22c55e)', healthy: true }
  return { label: source, color: 'var(--danger, #ef4444)', healthy: false }
}

const emptyNewSource = { source_key: '', display_name: '', url: '', unit: 'toman', extract_regex: '', priority: '100', timeout_s: '5' }

export default function ExchangeRateSection({ api }: ExchangeRateSectionProps) {
  const lang = useLang()
  const s = exchangeRateSectionStrings(lang)
  const f = fmt(lang)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [meta, setMeta] = useState<ExchangeRateMeta | null>(null)
  // Distinct from "no data yet": a failed load must not look like the
  // inert empty state once the toast fades.
  const [loadError, setLoadError] = useState<string | null>(null)

  const [flatMarkupDefault, setFlatMarkupDefault] = useState(2000)
  const [flatMarkupInput, setFlatMarkupInput] = useState('2000')
  const [savingFlatMarkup, setSavingFlatMarkup] = useState(false)

  const [builtin, setBuiltin] = useState<BuiltinSourceInfo[]>([])
  const [configured, setConfigured] = useState<ConfiguredSource[]>([])
  const [rowSaving, setRowSaving] = useState<string | null>(null)
  const [newSource, setNewSource] = useState(emptyNewSource)
  const [creatingSource, setCreatingSource] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const [rateRes, flatRes, sourcesRes] = await Promise.all([
        api('/api/admin/exchange-rate'),
        api('/api/admin/exchange-rate/flat-markup'),
        api('/api/admin/exchange-rate/sources'),
      ])
      const rateBody: ExchangeRateMeta = await rateRes.json()
      const flatBody = await flatRes.json()
      const sourcesBody = await sourcesRes.json()
      setMeta(rateBody)
      setFlatMarkupDefault(Number(flatBody.default_toman) || 2000)
      setFlatMarkupInput(String(flatBody.flat_markup_toman ?? 2000))
      setBuiltin(sourcesBody.builtin || [])
      setConfigured(sourcesBody.configured || [])
    } catch (err) {
      const msg = err instanceof Error && err.message !== 'unauthorized' ? err.message : s.loadErrorFallback
      setLoadError(msg)
      toast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }, [api, s.loadErrorFallback])

  useEffect(() => { load() }, [load])

  const refresh = async () => {
    setRefreshing(true)
    try {
      const res = await api('/api/admin/exchange-rate/refresh', { method: 'POST' })
      const body: ExchangeRateMeta = await res.json()
      setMeta(body)
      toast(s.refreshedToast, 'success')
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : s.refreshFailedToast, 'error')
    } finally {
      setRefreshing(false)
    }
  }

  const saveFlatMarkup = async () => {
    const v = Number(flatMarkupInput)
    if (!Number.isFinite(v) || v < 0) {
      toast(s.flatMarkupNegativeToast, 'error')
      return
    }
    setSavingFlatMarkup(true)
    try {
      await api('/api/admin/exchange-rate/flat-markup', { method: 'POST', body: JSON.stringify({ flat_markup_toman: v }) })
      toast(s.flatMarkupSavedToast, 'success')
      await load()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : s.flatMarkupSaveFailedToast, 'error')
    } finally {
      setSavingFlatMarkup(false)
    }
  }

  const patchSource = async (key: string, body: Record<string, unknown>) => {
    setRowSaving(key)
    try {
      await api(`/api/admin/exchange-rate/sources/${encodeURIComponent(key)}`, { method: 'PATCH', body: JSON.stringify(body) })
      await load()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : s.sourceUpdateFailedToast, 'error')
    } finally {
      setRowSaving(null)
    }
  }

  const deleteSource = async (key: string) => {
    if (!confirm(s.confirmDeleteSource(key))) return
    setRowSaving(key)
    try {
      await api(`/api/admin/exchange-rate/sources/${encodeURIComponent(key)}`, { method: 'DELETE' })
      toast(s.sourceDeletedToast, 'success')
      await load()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : s.sourceDeleteFailedToast, 'error')
    } finally {
      setRowSaving(null)
    }
  }

  const createSource = async () => {
    const priority = Number(newSource.priority)
    const timeout_s = Number(newSource.timeout_s)
    if (!newSource.source_key.trim() || !newSource.display_name.trim() || !newSource.url.trim() || !newSource.extract_regex.trim()) {
      toast(s.newSourceRequiredFieldsToast, 'error')
      return
    }
    if (!Number.isFinite(priority) || priority <= 0) {
      toast(s.priorityMustBePositiveToast, 'error')
      return
    }
    if (!Number.isFinite(timeout_s) || timeout_s <= 0 || timeout_s > 10) {
      toast(s.timeoutRangeToast, 'error')
      return
    }
    setCreatingSource(true)
    try {
      await api('/api/admin/exchange-rate/sources', {
        method: 'POST',
        body: JSON.stringify({ ...newSource, priority, timeout_s }),
      })
      toast(s.sourceAddedToast, 'success')
      setNewSource(emptyNewSource)
      await load()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : s.sourceAddFailedToast, 'error')
    } finally {
      setCreatingSource(false)
    }
  }

  const sm = meta ? sourceMeta(meta.source, configured, s) : null

  return (
    <div className="space-y-6">
      <SectionHeader title={s.title} subtitle={s.subtitle} />

      {loading ? (
        <div className="admin-card p-6 text-center text-sm text-muted">{s.loading}</div>
      ) : loadError ? (
        <div className="admin-card p-6 text-center text-sm" style={{ color: 'var(--danger, #ef4444)' }}>
          {loadError}
          <div className="mt-2">
            <button className="btn btn-sm" onClick={load}>
              <Icon name="refresh" size={14} />
              {s.retry}
            </button>
          </div>
        </div>
      ) : !meta ? (
        <div className="admin-card p-6 text-center text-sm text-muted">{s.noData}</div>
      ) : (
        <>
          <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            <StatCard icon="chart" label={s.statBareRate} value={f.price(Math.round(meta.rate_irt_bare))} color="var(--accent, #6366f1)" />
            <StatCard icon="plus" label={s.statFlatMarkup} value={f.price(Math.round(meta.flat_markup_irt))} color="var(--warning, #eab308)" />
            <StatCard icon="wallet" label={s.statEffectiveRate} value={f.price(Math.round(meta.rate_irt_effective))} color="var(--success, #22c55e)" />
          </div>

          <div className="admin-card">
            <div className="flex items-center justify-between gap-4 flex-wrap mb-4">
              <h3 className="font-semibold text-sm text-primary">{s.sourceAndTimingTitle}</h3>
              <button className="btn btn-sm" onClick={refresh} disabled={refreshing}>
                {refreshing ? (
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                ) : (<><Icon name="refresh" size={14} /><span>{s.refreshNow}</span></>)}
              </button>
            </div>

            <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
              <div>
                <p className="text-xs text-muted mb-1">{s.sourceLabel}</p>
                <span
                  className="badge"
                  title={sm && !sm.healthy ? s.unhealthyTooltip : undefined}
                  style={{ color: sm?.color, borderColor: sm?.color }}
                >
                  {sm?.label}
                </span>
                {sm && !sm.healthy && (
                  <p className="text-xs mt-1" style={{ color: sm.color }}>
                    {s.unhealthyWarning}
                  </p>
                )}
              </div>
              <div>
                <p className="text-xs text-muted mb-1">{s.lastFetchLabel}</p>
                <p className="text-sm text-primary">
                  {meta.fetched_at ? `${f.date(meta.fetched_at)} — ${f.time(meta.fetched_at)}` : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted mb-1">{s.cacheTtlLabel}</p>
                <p className="text-sm text-primary">
                  {meta.cache_ttl_remaining_s != null ? s.cacheTtlValue(f.num(meta.cache_ttl_remaining_s)) : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted mb-1">{s.globalMarkupPctLabel}</p>
                <p className="text-sm text-primary">{f.percent(meta.markup_pct)}</p>
              </div>
            </div>
          </div>

          <div className="admin-card">
            <p className="text-xs text-muted leading-6">
              {s.effectiveRateExplanation(
                f.price(Math.round(meta.rate_irt_bare)),
                f.price(Math.round(meta.flat_markup_irt)),
                f.price(Math.round(meta.rate_irt_effective)),
              )}
            </p>
          </div>

          {/* Flat markup edit */}
          <div className="admin-card">
            <h3 className="font-semibold text-sm text-primary mb-1">{s.flatMarkupTitle}</h3>
            <p className="text-xs text-muted mb-4">{s.flatMarkupDescription(f.price(flatMarkupDefault))}</p>
            <div className="flex items-end gap-3 flex-wrap">
              <Field label={s.flatMarkupFieldLabel}>
                <NumInput value={flatMarkupInput} onChange={setFlatMarkupInput} width={160} />
              </Field>
              <button className="btn btn-sm btn-primary" onClick={saveFlatMarkup} disabled={savingFlatMarkup}>
                {savingFlatMarkup ? '…' : (<><Icon name="check" size={14} /><span>{s.save}</span></>)}
              </button>
            </div>
          </div>

          {/* Sources */}
          <div className="admin-card">
            <h3 className="font-semibold text-sm text-primary mb-1">{s.sourcesTitle}</h3>
            <p className="text-xs text-muted mb-4">{s.sourcesDescription}</p>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-right text-xs text-muted border-b border-line">
                    <th className="py-2 pl-2">{s.colSource}</th>
                    <th className="py-2 pl-2">{s.colKind}</th>
                    <th className="py-2 pl-2">{s.colPriority}</th>
                    <th className="py-2 pl-2">{s.colStatus}</th>
                    <th className="py-2 pl-2">{s.colActions}</th>
                  </tr>
                </thead>
                <tbody>
                  {builtin.map((b) => (
                    <tr key={b.source_key} className="border-b border-line/50">
                      <td className="py-2 pl-2">{b.display_name}</td>
                      <td className="py-2 pl-2 text-xs text-muted">{s.hardcodedKind}</td>
                      <td className="py-2 pl-2 text-xs text-muted">—</td>
                      <td className="py-2 pl-2 text-xs text-muted" title={b.note}>{s.notEditable}</td>
                      <td className="py-2 pl-2 text-xs text-muted">—</td>
                    </tr>
                  ))}
                  {configured.map((c) => (
                    <tr key={c.source_key} className="border-b border-line/50">
                      <td className="py-2 pl-2">
                        {c.display_name}
                        {c.is_builtin && <span className="text-xs text-muted">{s.builtinSuffix}</span>}
                      </td>
                      <td className="py-2 pl-2 text-xs text-muted">
                        {c.kind === 'bonbast' ? s.kindBonbast : s.kindCustom(c.unit === 'rial' ? s.unitRial : s.unitToman)}
                      </td>
                      <td className="py-2 pl-2">
                        <input
                          className="input" type="number" min={1} defaultValue={c.priority}
                          style={{ maxWidth: 80 }}
                          onBlur={(e) => {
                            const v = Number(e.target.value)
                            if (Number.isFinite(v) && v > 0 && v !== c.priority) patchSource(c.source_key, { priority: v })
                          }}
                        />
                      </td>
                      <td className="py-2 pl-2">
                        <button
                          className="badge" disabled={rowSaving === c.source_key}
                          style={{ color: c.enabled ? 'var(--success, #22c55e)' : 'var(--danger, #ef4444)', borderColor: c.enabled ? 'var(--success, #22c55e)' : 'var(--danger, #ef4444)' }}
                          onClick={() => patchSource(c.source_key, { enabled: !c.enabled })}
                        >
                          {c.enabled ? s.enabled : s.disabled}
                        </button>
                      </td>
                      <td className="py-2 pl-2">
                        {c.deletable && (
                          <button className="btn btn-sm" disabled={rowSaving === c.source_key} onClick={() => deleteSource(c.source_key)} title={s.deleteTitle}>
                            <Icon name="trash" size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Add new source */}
            <div className="mt-6 pt-4 border-t border-line">
              <h4 className="font-semibold text-xs text-primary mb-3">{s.addSourceTitle}</h4>
              <p className="text-xs text-muted mb-3">{s.addSourceDescription}</p>
              <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
                <Field label={s.fieldKey}>
                  <input className="input" value={newSource.source_key} onChange={(e) => setNewSource((prev) => ({ ...prev, source_key: e.target.value.trim().toLowerCase() }))} placeholder="example_site" />
                </Field>
                <Field label={s.fieldDisplayName}>
                  <input className="input" value={newSource.display_name} onChange={(e) => setNewSource((prev) => ({ ...prev, display_name: e.target.value }))} placeholder="Example Site" />
                </Field>
                <Field label={s.fieldUnit}>
                  <select className="input" value={newSource.unit} onChange={(e) => setNewSource((prev) => ({ ...prev, unit: e.target.value }))}>
                    <option value="toman">{s.unitToman}</option>
                    <option value="rial">{s.unitRial}</option>
                  </select>
                </Field>
                <Field label={s.fieldPriority}>
                  <NumInput value={newSource.priority} onChange={(v) => setNewSource((prev) => ({ ...prev, priority: v }))} width={100} />
                </Field>
                <Field label={s.fieldTimeout}>
                  <NumInput value={newSource.timeout_s} onChange={(v) => setNewSource((prev) => ({ ...prev, timeout_s: v }))} width={100} />
                </Field>
              </div>
              <div className="grid gap-3 mt-3" style={{ gridTemplateColumns: '1fr' }}>
                <Field label={s.fieldUrl}>
                  <input className="input w-full" value={newSource.url} onChange={(e) => setNewSource((prev) => ({ ...prev, url: e.target.value }))} placeholder="https://example.com/usd-rate" />
                </Field>
                <Field label={s.fieldExtractRegex}>
                  <input className="input w-full" dir="ltr" value={newSource.extract_regex} onChange={(e) => setNewSource((prev) => ({ ...prev, extract_regex: e.target.value }))} placeholder={'USD\\s*=\\s*([\\d,]+)'} />
                </Field>
              </div>
              <button className="btn btn-sm btn-primary mt-3" onClick={createSource} disabled={creatingSource}>
                {creatingSource ? '…' : (<><Icon name="plus" size={14} /><span>{s.addSource}</span></>)}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
