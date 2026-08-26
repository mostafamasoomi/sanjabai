'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { AVAILABILITY_COLOR, AVAILABILITY_OPTIONS, availabilityLabel, type Availability } from './availability'
import { catalogFilterStrings } from './CatalogFilterBar.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   The one control strip for «عملیات کاتالوگ مدل‌ها»: filters and counters on
   the same line.

   These used to be four stacked blocks — a 4-card availability grid, then a
   3-card probe grid, then the warning, then the filter bar — which pushed the
   table itself below the fold on a laptop before a single model row was
   visible. Seven full-height StatCards to show seven integers is a poor trade
   for that much vertical space, so the counters are compact chips here and
   sit beside the controls that act on them.

   Own file because ModelOpsSection.tsx is past the project's 500-line cap.
   Presentational only: every value and setter is a prop, so this holds no
   state and the filtering logic stays in one place, next to the rows.
   ═══════════════════════════════════════════════════════════════════════════ */

export type ProbeFilter = 'all' | 'confirmed' | 'unprobed' | 'ready'

interface CatalogFilterBarProps {
  search: string
  onSearch: (v: string) => void
  availFilter: 'all' | Availability
  onAvailFilter: (v: 'all' | Availability) => void
  probeFilter: ProbeFilter
  onProbeFilter: (v: ProbeFilter) => void
  onReload: () => void
  loading: boolean
  matched: number
  total: number
  /** model_catalog.availability counts, keyed by the raw enum value. */
  counts: Record<string, number>
  /** Counts derived from model_health_state.last_ok_at — see ModelOpsSection. */
  probeCounts: { confirmed: number; parkedConfirmed: number; ready: number }
}

/** A counter as a chip rather than a card: a coloured dot, a label, a number.
 *  `tabular-nums` so the digits do not shift width as the counts change
 *  during a bulk live test. */
function CountChip({ color, label, value, num }: {
  color: string; label: string; value: number; num: (n: number) => string
}) {
  return (
    <span
      className="inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs whitespace-nowrap"
      style={{ background: `${color}12`, border: `1px solid ${color}33` }}
    >
      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} aria-hidden />
      <span className="text-muted">{label}</span>
      <span className="font-bold text-primary tabular-nums">{num(value)}</span>
    </span>
  )
}

function Divider() {
  return <span className="h-6 w-px shrink-0" style={{ background: 'var(--border)' }} aria-hidden />
}

export default function CatalogFilterBar({
  search, onSearch, availFilter, onAvailFilter, probeFilter, onProbeFilter,
  onReload, loading, matched, total, counts, probeCounts,
}: CatalogFilterBarProps) {
  const lang = useLang()
  const s = catalogFilterStrings(lang)
  const f = fmt(lang)
  const chip = (n: number) => f.num(n)

  // No `dir` of its own any more: it inherits from the panel root, which
  // follows the language. A hard-coded dir="rtl" here put the English
  // controls in a right-to-left strip inside a left-to-right panel.
  return (
    <div className="admin-card admin-row gap-3">
      <input
        className="input"
        placeholder={s.searchPlaceholder}
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        style={{ minWidth: 200, flex: '1 1 200px' }}
      />
      <select
        className="input"
        value={availFilter}
        onChange={(e) => onAvailFilter(e.target.value as 'all' | Availability)}
        style={{ maxWidth: 160 }}
      >
        <option value="all">{s.allAvailability}</option>
        {AVAILABILITY_OPTIONS.map((a) => (
          <option key={a} value={a}>{availabilityLabel(a, lang)}</option>
        ))}
      </select>
      <select
        className="input"
        value={probeFilter}
        onChange={(e) => onProbeFilter(e.target.value as ProbeFilter)}
        style={{ maxWidth: 190 }}
      >
        <option value="all">{s.allModels}</option>
        <option value="confirmed">{s.probeConfirmed}</option>
        <option value="unprobed">{s.probeUnconfirmed}</option>
        <option value="ready">{s.probeReady}</option>
      </select>
      <button className="btn btn-sm" onClick={onReload} disabled={loading}>
        <Icon name="refresh" size={14} /> {s.reload}
      </button>
      <span className="text-xs text-muted whitespace-nowrap">
        {s.matched(f.num(matched), f.num(total))}
      </span>

      <Divider />

      <CountChip color={AVAILABILITY_COLOR.available} label={s.available} value={counts.available || 0} num={chip} />
      <CountChip color={AVAILABILITY_COLOR.degraded} label={s.degraded} value={counts.degraded || 0} num={chip} />
      <CountChip color={AVAILABILITY_COLOR.maintenance} label={s.maintenance} value={counts.maintenance || 0} num={chip} />
      <CountChip color={AVAILABILITY_COLOR.disabled} label={s.disabled} value={counts.disabled || 0} num={chip} />

      <Divider />

      {/* The three the panel had no way to show before: measured against
          model_health_state.last_ok_at, not model_catalog.last_verified_at. */}
      <CountChip color={AVAILABILITY_COLOR.available} label={s.confirmed} value={probeCounts.confirmed} num={chip} />
      <CountChip color={AVAILABILITY_COLOR.degraded} label={s.healthyUnserved} value={probeCounts.parkedConfirmed} num={chip} />
      <CountChip color="var(--accent, #6366f1)" label={s.ready} value={probeCounts.ready} num={chip} />
    </div>
  )
}
