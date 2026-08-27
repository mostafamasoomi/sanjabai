/* ═══════════════════════════════════════════════════════════════════════════
   Pure chart math for the admin chart kit. No React, no DOM — everything in
   this file is unit-tested by frontend/tests/lib/chartUtils.test.ts.

   Lineage: `buildSharedPoints` below is the generalization of the private
   helper of the same name in ../../sections/AnalyticsSection.tsx (line ~97).
   The original normalizes against `0..sharedMax` only — no negative values,
   no gaps, fixed viewBox constants baked in. This one keeps its defining
   property (several series drawn against ONE shared scale so a series near
   zero visibly looks near zero) and adds: a shared {min,max} extent so net
   profit below zero draws below the zero line, null gaps that break the
   polyline instead of lying through missing days (the gap-skipping idea
   comes from MonitoringCharts.tsx::buildSegments), and a caller-supplied
   plot box instead of module constants. AnalyticsSection keeps its local
   copy — that file is outside this packet's scope.

   Data contract (deliberately generic — the analytics endpoint is wired in
   a later packet): a chart is a shared category axis (`labels`, e.g. days)
   plus N series whose `values` align to it by index. Money values are RAW
   INTEGER TOMANS end to end; nothing here multiplies or divides a value —
   scaling happens only in coordinate space.
   ═══════════════════════════════════════════════════════════════════════════ */

/** One drawable series, values aligned by index to the chart's labels.
 *  `null` = no measurement for that slot (drawn as a gap, never as zero). */
export interface ChartSeries {
  id: string
  label: string
  values: (number | null)[]
  /** Derived/estimated data (e.g. margin computed from a price assumption)
   *  — charts must visibly mark it so it is never read as measured. */
  estimated?: boolean
}

export interface Extent {
  min: number
  max: number
}

export interface NiceScale extends Extent {
  step: number
  ticks: number[]
}

/** The drawable area in SVG user units. `padY` keeps strokes at the extremes
 *  from being clipped by the viewBox edge. */
export interface PlotBox {
  width: number
  height: number
  padX?: number
  padY?: number
}

/** "Nice number" ≥/≈ `range`: 1, 2 or 5 times a power of ten (Graphics Gems). */
function niceNum(range: number, round: boolean): number {
  const exp = Math.floor(Math.log10(range))
  const frac = range / 10 ** exp
  let nice: number
  if (round) {
    nice = frac < 1.5 ? 1 : frac < 3 ? 2 : frac < 7 ? 5 : 10
  } else {
    nice = frac <= 1 ? 1 : frac <= 2 ? 2 : frac <= 5 ? 5 : 10
  }
  return nice * 10 ** exp
}

/** Min/max across every finite value of every series. `includeZero` (default
 *  true) anchors the extent at zero — an axis that starts at the minimum
 *  makes a flat series look dramatic, which is exactly the kind of lie the
 *  admin money charts must not tell. All-null/empty input → {0, 0}. */
export function seriesExtent(series: ChartSeries[], includeZero = true): Extent {
  let min = Infinity
  let max = -Infinity
  for (const s of series) {
    for (const v of s.values) {
      if (v == null || !Number.isFinite(v)) continue
      if (v < min) min = v
      if (v > max) max = v
    }
  }
  if (min === Infinity) {
    min = 0
    max = 0
  }
  if (includeZero) {
    min = Math.min(min, 0)
    max = Math.max(max, 0)
  }
  return { min, max }
}

/** Expands an extent to rounded bounds and generates axis ticks. Handles the
 *  degenerate cases: all-zero data (→ 0..1), a single repeated value, and
 *  min > max (swapped). When min < 0 < max, zero is always one of the ticks
 *  (both bounds are multiples of `step`), so the zero line can sit exactly
 *  on a gridline. */
export function niceScale(extent: Extent, maxTicks = 5): NiceScale {
  let { min, max } = extent
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    min = 0
    max = 1
  }
  if (min > max) [min, max] = [max, min]
  if (min === max) {
    // Flat data still needs a real axis: grow away from the value, toward
    // zero when possible so the value's sign stays readable.
    if (min === 0) max = 1
    else if (min > 0) min = 0
    else max = 0
  }
  const range = niceNum(max - min, false)
  const step = niceNum(range / (Math.max(2, maxTicks) - 1), true)
  // Round the tick values to the step's own precision — naive `lo + i*step`
  // accumulates float noise (0.30000000000000004) that would leak into labels.
  const decimals = Math.max(0, -Math.floor(Math.log10(step)))
  const lo = Math.floor(min / step) * step
  const hi = Math.ceil(max / step) * step
  const ticks: number[] = []
  for (let v = lo; v <= hi + step / 2; v += step) {
    ticks.push(Number(v.toFixed(decimals)))
  }
  return { min: Number(lo.toFixed(decimals)), max: Number(hi.toFixed(decimals)), step, ticks }
}

/** Category index → x in SVG user units. A single point sits centered. */
export function indexToX(i: number, count: number, box: PlotBox): number {
  const padX = box.padX ?? 0
  const inner = box.width - 2 * padX
  if (count <= 1) return padX + inner / 2
  return padX + (i / (count - 1)) * inner
}

/** Value → y in SVG user units against a shared scale. SVG y grows downward,
 *  so `scale.max` maps to the top pad and `scale.min` to the bottom — a
 *  negative value lands BELOW the y of zero. Degenerate scale (min === max)
 *  maps everything to the vertical center rather than dividing by zero. */
export function valueToY(v: number, scale: Extent, box: PlotBox): number {
  const padY = box.padY ?? 0
  const inner = box.height - 2 * padY
  const range = scale.max - scale.min
  const t = range === 0 ? 0.5 : (v - scale.min) / range
  return box.height - padY - t * inner
}

const round2 = (n: number): number => Math.round(n * 100) / 100

/** Polyline `points` strings for one series against a SHARED scale (see the
 *  header comment for how this generalizes AnalyticsSection's original).
 *  Returns one string per contiguous run of finite values: a null in the
 *  middle breaks the line into segments instead of interpolating across
 *  missing data. */
export function buildSharedPoints(
  values: (number | null)[],
  scale: Extent,
  box: PlotBox,
): string[] {
  const segments: string[] = []
  let current: string[] = []
  values.forEach((v, i) => {
    if (v == null || !Number.isFinite(v)) {
      if (current.length > 0) {
        segments.push(current.join(' '))
        current = []
      }
      return
    }
    const x = round2(indexToX(i, values.length, box))
    const y = round2(valueToY(v, scale, box))
    current.push(`${x},${y}`)
  })
  if (current.length > 0) segments.push(current.join(' '))
  return segments
}

/** Which category indices get an axis label. A 90-day window must not render
 *  90 overlapping date labels: at most `maxTicks` survive, always including
 *  the first and last index, evenly strided in between. A penultimate tick
 *  that would crowd the final one (closer than half a stride) is dropped. */
export function tickIndices(count: number, maxTicks = 7): number[] {
  if (count <= 0) return []
  const cap = Math.max(2, maxTicks)
  if (count <= cap) return Array.from({ length: count }, (_, i) => i)
  const step = Math.ceil((count - 1) / (cap - 1))
  const out: number[] = []
  for (let i = 0; i < count - 1; i += step) out.push(i)
  if (out.length > 0 && count - 1 - out[out.length - 1] < step / 2) out.pop()
  out.push(count - 1)
  return out
}

/** One bar segment of a stacked column: series index plus the [v0, v1] value
 *  interval it covers (v0 < v1, both in data units, not pixels). */
export interface StackSegment {
  seriesIndex: number
  v0: number
  v1: number
}

/** Signed stacking, one column per category index: positive values accumulate
 *  upward from zero, negative values downward — so a stacked money chart with
 *  a below-zero net still reads correctly instead of negative bars being
 *  subtracted from the positive pile. Zero/null values produce no segment. */
export function stackSeries(series: ChartSeries[]): StackSegment[][] {
  const count = series.reduce((n, s) => Math.max(n, s.values.length), 0)
  const columns: StackSegment[][] = []
  for (let i = 0; i < count; i++) {
    let pos = 0
    let neg = 0
    const column: StackSegment[] = []
    series.forEach((s, seriesIndex) => {
      const v = s.values[i]
      if (v == null || !Number.isFinite(v) || v === 0) return
      if (v > 0) {
        column.push({ seriesIndex, v0: pos, v1: pos + v })
        pos += v
      } else {
        column.push({ seriesIndex, v0: neg + v, v1: neg })
        neg += v
      }
    })
    columns.push(column)
  }
  return columns
}

/** Extent of the stacked totals (always spanning zero) — the scale a stacked
 *  bar chart must use; `seriesExtent` would size the axis to individual
 *  values, not the stacked reach. */
export function stackedExtent(series: ChartSeries[]): Extent {
  let min = 0
  let max = 0
  for (const column of stackSeries(series)) {
    for (const seg of column) {
      if (seg.v0 < min) min = seg.v0
      if (seg.v1 > max) max = seg.v1
    }
  }
  return { min, max }
}

/** True when there is nothing drawable — no labels, no series, or every value
 *  null/non-finite. Charts render an explicit empty state on this, never an
 *  axis around nothing. */
export function isEmptySeries(labels: string[], series: ChartSeries[]): boolean {
  if (labels.length === 0 || series.length === 0) return true
  return !series.some((s) => s.values.some((v) => v != null && Number.isFinite(v)))
}
