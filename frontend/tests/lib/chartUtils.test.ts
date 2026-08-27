import { describe, it, expect } from 'vitest'

import {
  buildSharedPoints,
  indexToX,
  isEmptySeries,
  niceScale,
  seriesExtent,
  stackSeries,
  stackedExtent,
  tickIndices,
  valueToY,
  type ChartSeries,
  type PlotBox,
} from '../../app/admin/components/charts/chartUtils'

/* Unit tests for the pure chart math behind the admin chart kit
 * (app/admin/components/charts/). Same setup note as upstreamOverhead.test.ts:
 * these helpers live in a plain .ts module precisely so vitest can test them
 * without touching any .tsx component.
 *
 * The negative-value and shared-scale cases matter most: net profit can be
 * below zero, and money series drawn on one axis must stay comparable — a
 * regression in either silently draws a wrong chart that still "looks fine". */

const BOX: PlotBox = { width: 600, height: 160, padX: 0, padY: 6 }

const series = (values: (number | null)[], id = 's'): ChartSeries => ({
  id,
  label: id,
  values,
})

/** Parses "x,y x,y ..." into [x, y] pairs. */
function parsePoints(segment: string): Array<[number, number]> {
  return segment.split(' ').map((p) => {
    const [x, y] = p.split(',').map(Number)
    return [x, y]
  })
}

describe('seriesExtent', () => {
  it('spans all finite values across all series and anchors at zero', () => {
    const ext = seriesExtent([series([120, 300, null]), series([-50, 40])])
    expect(ext).toEqual({ min: -50, max: 300 })
  })

  it('always includes zero by default even for all-positive data', () => {
    expect(seriesExtent([series([100, 200])])).toEqual({ min: 0, max: 200 })
  })

  it('can skip the zero anchor when asked', () => {
    expect(seriesExtent([series([100, 200])], false)).toEqual({ min: 100, max: 200 })
  })

  it('returns {0,0} for empty or all-null input', () => {
    expect(seriesExtent([])).toEqual({ min: 0, max: 0 })
    expect(seriesExtent([series([null, null])])).toEqual({ min: 0, max: 0 })
  })
})

describe('niceScale', () => {
  it('produces ascending round ticks that cover the extent', () => {
    const sc = niceScale({ min: 0, max: 97 })
    expect(sc.min).toBeLessThanOrEqual(0)
    expect(sc.max).toBeGreaterThanOrEqual(97)
    expect(sc.ticks[0]).toBe(sc.min)
    expect(sc.ticks[sc.ticks.length - 1]).toBe(sc.max)
    for (let i = 1; i < sc.ticks.length; i++) {
      expect(sc.ticks[i]).toBeGreaterThan(sc.ticks[i - 1])
    }
  })

  it('survives all-zero data with a real 0..1 axis, no NaN', () => {
    const sc = niceScale(seriesExtent([series([0, 0, 0])]))
    expect(sc.min).toBe(0)
    expect(sc.max).toBeGreaterThan(0)
    expect(sc.ticks.every((t) => Number.isFinite(t))).toBe(true)
  })

  it('survives a single-point extent (min === max !== 0)', () => {
    const sc = niceScale({ min: 500, max: 500 })
    expect(sc.min).toBeLessThanOrEqual(0)
    expect(sc.max).toBeGreaterThanOrEqual(500)
    expect(sc.step).toBeGreaterThan(0)
  })

  it('places zero exactly on a tick when the range spans zero', () => {
    const sc = niceScale({ min: -500, max: 1000 })
    expect(sc.ticks).toContain(0)
    expect(sc.min).toBeLessThanOrEqual(-500)
    expect(sc.max).toBeGreaterThanOrEqual(1000)
  })

  it('emits clean fractional ticks without float noise', () => {
    const sc = niceScale({ min: 0, max: 1 })
    for (const t of sc.ticks) {
      // e.g. 0.30000000000000004 would fail this stringification check
      expect(String(t).length).toBeLessThanOrEqual(4)
    }
  })
})

describe('valueToY (negative values / orientation)', () => {
  const scale = { min: -100, max: 300 }

  it('maps larger values HIGHER on screen (smaller y) — SVG y grows down', () => {
    const yMin = valueToY(-100, scale, BOX)
    const yZero = valueToY(0, scale, BOX)
    const yMax = valueToY(300, scale, BOX)
    expect(yMin).toBeGreaterThan(yZero) // negative value sits below zero line
    expect(yZero).toBeGreaterThan(yMax)
    expect(yMax).toBe(6) // top pad
    expect(yMin).toBe(154) // height - pad
  })

  it('puts the zero line proportionally, not at the bottom, when min < 0', () => {
    const yZero = valueToY(0, scale, BOX)
    expect(yZero).toBeLessThan(154)
    expect(yZero).toBeGreaterThan(6)
  })

  it('does not divide by zero on a degenerate scale', () => {
    const y = valueToY(5, { min: 5, max: 5 }, BOX)
    expect(Number.isFinite(y)).toBe(true)
  })
})

describe('indexToX', () => {
  it('centers a single point', () => {
    expect(indexToX(0, 1, BOX)).toBe(300)
  })

  it('spreads endpoints across the full inner width', () => {
    expect(indexToX(0, 30, BOX)).toBe(0)
    expect(indexToX(29, 30, BOX)).toBe(600)
  })
})

describe('buildSharedPoints', () => {
  const scale = { min: 0, max: 100 }

  it('keeps two series comparable on one shared scale: equal value, equal y', () => {
    const [a] = buildSharedPoints([50, 100], scale, BOX)
    const [b] = buildSharedPoints([50, 25], scale, BOX)
    const ya = parsePoints(a)[0][1]
    const yb = parsePoints(b)[0][1]
    expect(ya).toBe(yb)
  })

  it('breaks the line at nulls instead of interpolating across a gap', () => {
    const segments = buildSharedPoints([10, null, 30, 40], scale, BOX)
    expect(segments).toHaveLength(2)
    expect(parsePoints(segments[0])).toHaveLength(1)
    expect(parsePoints(segments[1])).toHaveLength(2)
  })

  it('draws negative values below the zero line', () => {
    const negScale = { min: -100, max: 100 }
    const [seg] = buildSharedPoints([-100, 0, 100], negScale, BOX)
    const pts = parsePoints(seg)
    const yNeg = pts[0][1]
    const yZero = pts[1][1]
    const yPos = pts[2][1]
    expect(yNeg).toBeGreaterThan(yZero)
    expect(yZero).toBeGreaterThan(yPos)
  })

  it('centers a single-point series', () => {
    const segments = buildSharedPoints([42], scale, BOX)
    expect(segments).toHaveLength(1)
    expect(parsePoints(segments[0])[0][0]).toBe(300)
  })

  it('returns no segments for all-null input', () => {
    expect(buildSharedPoints([null, null], scale, BOX)).toHaveLength(0)
  })
})

describe('tickIndices (date-axis thinning)', () => {
  it('thins a 90-day window to at most maxTicks, keeping both endpoints', () => {
    const idx = tickIndices(90, 7)
    expect(idx.length).toBeLessThanOrEqual(7)
    expect(idx[0]).toBe(0)
    expect(idx[idx.length - 1]).toBe(89)
    for (let i = 1; i < idx.length; i++) {
      expect(idx[i]).toBeGreaterThan(idx[i - 1])
    }
  })

  it('keeps every index when there is room', () => {
    expect(tickIndices(5, 7)).toEqual([0, 1, 2, 3, 4])
  })

  it('handles empty and single-point axes', () => {
    expect(tickIndices(0, 7)).toEqual([])
    expect(tickIndices(1, 7)).toEqual([0])
  })

  it('never lets the last stride crowd the final label', () => {
    for (let count = 2; count <= 120; count++) {
      const idx = tickIndices(count, 7)
      const last = idx[idx.length - 1]
      const prev = idx[idx.length - 2]
      expect(last).toBe(count - 1)
      if (prev != null && count > 7) {
        const step = Math.ceil((count - 1) / 6)
        expect(last - prev).toBeGreaterThanOrEqual(step / 2)
      }
    }
  })
})

describe('stackSeries / stackedExtent (signed stacking)', () => {
  it('stacks positives up from zero and negatives down', () => {
    const [column] = stackSeries([
      series([100], 'rev'),
      series([-40], 'cost'),
      series([50], 'other'),
    ])
    expect(column).toEqual([
      { seriesIndex: 0, v0: 0, v1: 100 },
      { seriesIndex: 1, v0: -40, v1: 0 },
      { seriesIndex: 2, v0: 100, v1: 150 },
    ])
  })

  it('stacks a second negative below the first', () => {
    const [column] = stackSeries([series([-30], 'a'), series([-20], 'b')])
    expect(column).toEqual([
      { seriesIndex: 0, v0: -30, v1: 0 },
      { seriesIndex: 1, v0: -50, v1: -30 },
    ])
  })

  it('skips nulls and zeros without breaking the running totals', () => {
    const [column] = stackSeries([series([null], 'a'), series([0], 'b'), series([70], 'c')])
    expect(column).toEqual([{ seriesIndex: 2, v0: 0, v1: 70 }])
  })

  it('sizes the stacked extent to the stacked reach, spanning zero', () => {
    const ext = stackedExtent([series([100, 10]), series([-40, -5]), series([50, 10])])
    expect(ext).toEqual({ min: -40, max: 150 })
  })
})

describe('isEmptySeries', () => {
  it('is empty for no labels, no series, or all-null values', () => {
    expect(isEmptySeries([], [series([1])])).toBe(true)
    expect(isEmptySeries(['a'], [])).toBe(true)
    expect(isEmptySeries(['a', 'b'], [series([null, null])])).toBe(true)
  })

  it('is not empty when any finite value exists — including zero', () => {
    expect(isEmptySeries(['a', 'b'], [series([null, 0])])).toBe(false)
  })
})
