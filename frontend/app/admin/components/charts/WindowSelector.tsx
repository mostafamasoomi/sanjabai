'use client'

import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { chartsStrings } from './charts.strings'

/* Day-window segmented control for the admin charts. Controlled component:
 * the parent owns the window and refetches on change (AnalyticsSection wires
 * it to GET /admin/analytics/timeseries?days=). The set below mirrors the
 * backend whitelist WINDOW_DAYS in backend/admin_analytics_timeseries.py —
 * offering a value the endpoint would silently fall back from would show the
 * admin a selected «۱ روز» over 30 days of data. Native <button>s inside a
 * role="group" keep it keyboard-accessible for free (Tab between,
 * Enter/Space activate); `aria-pressed` announces the active segment.
 * Styling reuses the global `.btn` classes as-is — the base `.btn` already
 * carries its own background and border in globals.css, and the active
 * segment switches to `.btn-primary`, which sets its own fill; nothing is
 * re-styled here. */

export type ChartWindow = 1 | 7 | 30 | 60 | 90

const WINDOWS: readonly ChartWindow[] = [1, 7, 30, 60, 90]

export interface WindowSelectorProps {
  value: ChartWindow
  onChange: (window: ChartWindow) => void
  disabled?: boolean
}

export default function WindowSelector({ value, onChange, disabled }: WindowSelectorProps) {
  const lang = useLang()
  const s = chartsStrings(lang)
  const f = fmt(lang)

  return (
    <div role="group" aria-label={s.windowGroupLabel} className="flex items-center gap-1">
      {WINDOWS.map((w) => (
        <button
          key={w}
          type="button"
          className={`btn btn-sm${value === w ? ' btn-primary' : ''}`}
          aria-pressed={value === w}
          aria-label={s.windowOptionAria(f.num(w))}
          disabled={disabled}
          onClick={() => {
            if (w !== value) onChange(w)
          }}
        >
          {s.windowDays(f.num(w))}
        </button>
      ))}
    </div>
  )
}
