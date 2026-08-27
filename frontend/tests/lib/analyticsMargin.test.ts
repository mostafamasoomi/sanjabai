import { describe, it, expect } from 'vitest'
import {
  coverageDisplay,
  marginDisplay,
  usageMarginValues,
  type DailyMargin,
} from '@/app/admin/components/AnalyticsCharts'
import { analyticsChartsStrings } from '@/app/admin/components/AnalyticsCharts.strings'
import { fmt } from '@/lib/i18n'

/* The test behind the null-margin contract.
 *
 * GET /admin/analytics/timeseries returns `usage_margin: null` (and per-row
 * `margin: null`) for any bucket that is not fully cost-measured — today
 * that is ALL pre-cutover history. The UI must render that null as the
 * unmeasured word, never as «۰ تومان»: a `?? 0` anywhere on this path draws
 * a fake break-even past out of history that simply predates measurement.
 * tsc cannot catch that mutation (`number | null` coalesced to `number` is
 * perfectly well-typed), so this file exists. It pins the two helpers every
 * margin display and every margin chart series in AnalyticsCharts.tsx is
 * routed through. */

const fa = fmt('fa')
const en = fmt('en')
const sFa = analyticsChartsStrings('fa')
const sEn = analyticsChartsStrings('en')

describe('null-margin contract (marginDisplay)', () => {
  it('renders a null margin as the unmeasured word, never a zero', () => {
    expect(marginDisplay(null, fa.price, sFa.unmeasured)).toBe(sFa.unmeasured)
    expect(marginDisplay(undefined, fa.price, sFa.unmeasured)).toBe(sFa.unmeasured)
    expect(marginDisplay(null, en.price, sEn.unmeasured)).toBe(sEn.unmeasured)
    // And specifically not any formatted zero — the exact lie `?? 0` tells.
    expect(marginDisplay(null, fa.price, sFa.unmeasured)).not.toBe(fa.price(0))
    expect(marginDisplay(null, fa.price, sFa.unmeasured)).not.toContain('۰')
  })

  it('renders a REAL zero margin as zero — null and zero are different facts', () => {
    expect(marginDisplay(0, fa.price, sFa.unmeasured)).toBe(fa.price(0))
  })

  it('renders a negative margin with its sign, not clamped or hidden', () => {
    expect(marginDisplay(-1500, fa.price, sFa.unmeasured)).toBe(fa.price(-1500))
    expect(marginDisplay(-1500, en.price, sEn.unmeasured)).toContain('−')
  })

  it('renders a positive margin through the money formatter unchanged', () => {
    expect(marginDisplay(9995511, fa.price, sFa.unmeasured)).toBe(fa.price(9995511))
  })
})

describe('null-margin contract (chart series)', () => {
  it('preserves nulls so the kit draws a gap, not a fake zero line', () => {
    const rows: DailyMargin[] = [
      { day: '2026-08-01', usage_margin: null, net: null },
      { day: '2026-08-02', usage_margin: 120, net: 80 },
      { day: '2026-08-03', usage_margin: -40, net: null },
    ]
    expect(usageMarginValues(rows)).toEqual([null, 120, -40])
  })

  it('an all-null window stays all-null (139 pre-cutover events = no line at all)', () => {
    const rows: DailyMargin[] = Array.from({ length: 5 }, (_, i) => ({
      day: `2026-07-0${i + 1}`,
      usage_margin: null,
      net: null,
    }))
    expect(usageMarginValues(rows).every((v) => v === null)).toBe(true)
  })
})

describe('coverage display', () => {
  it('shows the 0..1 ratio as a percent', () => {
    expect(coverageDisplay(0.5, fa.percent)).toBe(fa.percent(50))
    expect(coverageDisplay(0, fa.percent)).toBe(fa.percent(0))
    expect(coverageDisplay(1, en.percent)).toBe(en.percent(100))
  })
})
