'use client'

import { useMemo, useState } from 'react'
import { useLang } from '@/components/LanguageToggle'
import { dirFor, fmt } from '@/lib/i18n'
import { chartsStrings } from './charts.strings'
import {
  CHART_GRID_COLOR,
  CHART_TOOLTIP_BG,
  CHART_TOOLTIP_BORDER,
  CHART_ZERO_COLOR,
  metricColor,
  type ChartMetric,
} from './chartTheme'
import {
  isEmptySeries,
  niceScale,
  seriesExtent,
  stackSeries,
  stackedExtent,
  tickIndices,
  valueToY,
  type ChartSeries,
  type PlotBox,
} from './chartUtils'

/* ═══════════════════════════════════════════════════════════════════════════
   Grouped/stacked bar chart, hand-written SVG — recharts is BANNED (see
   ../AdminCharts.tsx). Same RTL contract as LineChart: the plot sits inside
   `dir="ltr"` so categories run oldest→newest left-to-right, legend and
   tooltip stay in the language's direction.

   Negative values are first-class in BOTH modes: every bar grows away from
   the zero line (not from the bottom edge), and stacked columns stack
   positives upward and negatives downward via chartUtils.stackSeries — the
   stacked scale comes from stackedExtent so the axis fits the stacked reach,
   not the individual values. An `estimated` series renders hatched-light
   (dashed outline, translucent fill) and its label carries the suffix.
   ═══════════════════════════════════════════════════════════════════════════ */

export interface BarChartSeries extends ChartSeries {
  metric: ChartMetric
}

export interface BarChartProps {
  labels: string[]
  series: BarChartSeries[]
  mode: 'grouped' | 'stacked'
  ariaLabel: string
  /** Tooltip formatter — money charts pass fmt(lang).price; raw integer
   *  tomans in, never rescaled here. Defaults to fmt.num. */
  formatValue?: (v: number) => string
  /** Y-tick formatter, defaults to fmt.compact. */
  formatTick?: (v: number) => string
  height?: number
  maxXTicks?: number
}

const SVG_W = 600
const Y_AXIS_WIDTH = '4rem'
/** Fraction of each category slot occupied by bars (rest is gap). */
const SLOT_FILL = 0.7

export default function BarChart({
  labels,
  series,
  mode,
  ariaLabel,
  formatValue,
  formatTick,
  height = 160,
  maxXTicks = 7,
}: BarChartProps) {
  const lang = useLang()
  const s = chartsStrings(lang)
  const f = fmt(lang)
  const [hover, setHover] = useState<number | null>(null)

  const fmtValue = formatValue ?? f.num
  const fmtTick = formatTick ?? ((v: number) => f.compact(v))

  const box: PlotBox = useMemo(
    () => ({ width: SVG_W, height, padX: 0, padY: 6 }),
    [height],
  )
  const scale = useMemo(
    () => niceScale(mode === 'stacked' ? stackedExtent(series) : seriesExtent(series)),
    [mode, series],
  )
  const columns = useMemo(
    () => (mode === 'stacked' ? stackSeries(series) : null),
    [mode, series],
  )

  if (isEmptySeries(labels, series)) {
    return <div className="text-center text-[var(--text-muted)] py-8 text-sm">{s.empty}</div>
  }

  const count = labels.length
  const hasNegative = scale.min < 0
  const zeroY = valueToY(0, scale, box)
  const xTicks = tickIndices(count, maxXTicks)
  const slot = SVG_W / count
  const innerW = slot * SLOT_FILL
  const slotPad = (slot - innerW) / 2

  const barStyle = (metric: ChartMetric, estimated: boolean | undefined) =>
    estimated
      ? {
          fill: metricColor(metric),
          fillOpacity: 0.45,
          stroke: metricColor(metric),
          strokeDasharray: '4 3',
          strokeWidth: 1,
        }
      : { fill: metricColor(metric), fillOpacity: 0.85 }

  /** A rect spanning the value interval [v0, v1] within category `i`. */
  const rectFor = (i: number, v0: number, v1: number, x: number, w: number) => {
    const y0 = valueToY(v0, scale, box)
    const y1 = valueToY(v1, scale, box)
    return { x: x, y: Math.min(y0, y1), width: w, height: Math.abs(y0 - y1) }
  }

  const onMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    if (rect.width === 0) return
    const frac = (e.clientX - rect.left) / rect.width
    setHover(Math.max(0, Math.min(count - 1, Math.floor(frac * count))))
  }

  const hoverPct = hover != null ? ((hover * slot + slot / 2) / SVG_W) * 100 : null

  return (
    <div>
      {/* Legend — surrounding RTL flow. */}
      <div className="flex flex-wrap items-center gap-4 mb-3">
        {series.map((sr) => (
          <span key={sr.id} className="flex items-center gap-1 text-xs">
            <span
              className="inline-block w-2.5 h-2.5 rounded-sm"
              style={
                sr.estimated
                  ? { border: `2px dashed ${metricColor(sr.metric)}` }
                  : { background: metricColor(sr.metric) }
              }
            />
            {sr.label}
            {sr.estimated ? s.estimatedSuffix : ''}
          </span>
        ))}
      </div>

      {/* Plot — LTR so the axes are not mirrored by the RTL panel. */}
      <div dir="ltr" className="flex">
        <div className="relative shrink-0" style={{ width: Y_AXIS_WIDTH, height: `${height}px` }}>
          {scale.ticks.map((t) => (
            <span
              key={t}
              className="absolute left-0 right-1 text-left text-[10px] text-[var(--text-muted)] leading-none"
              style={{
                top: `${(valueToY(t, scale, box) / height) * 100}%`,
                transform: 'translateY(-50%)',
              }}
            >
              {fmtTick(t)}
            </span>
          ))}
        </div>

        <div className="relative flex-1 min-w-0" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
          <svg
            role="img"
            aria-label={ariaLabel}
            viewBox={`0 0 ${SVG_W} ${height}`}
            preserveAspectRatio="none"
            style={{ width: '100%', height: `${height}px`, display: 'block' }}
          >
            {scale.ticks.map((t) =>
              hasNegative && t === 0 ? null : (
                <line
                  key={`grid-${t}`}
                  x1={0}
                  x2={SVG_W}
                  y1={valueToY(t, scale, box)}
                  y2={valueToY(t, scale, box)}
                  stroke={CHART_GRID_COLOR}
                  strokeWidth={1}
                  vectorEffect="non-scaling-stroke"
                />
              ),
            )}
            {hover != null && (
              <rect
                x={hover * slot}
                y={0}
                width={slot}
                height={height}
                fill={CHART_GRID_COLOR}
                fillOpacity={0.35}
              />
            )}
            {mode === 'grouped' &&
              labels.map((_, i) => {
                const barW = innerW / series.length
                return series.map((sr, si) => {
                  const v = sr.values[i]
                  if (v == null || !Number.isFinite(v) || v === 0) return null
                  const r = rectFor(i, 0, v, i * slot + slotPad + si * barW, Math.max(barW - 1, 1))
                  return <rect key={`${sr.id}-${i}`} {...r} {...barStyle(sr.metric, sr.estimated)} />
                })
              })}
            {mode === 'stacked' &&
              columns?.map((column, i) =>
                column.map((seg) => {
                  const sr = series[seg.seriesIndex]
                  const r = rectFor(i, seg.v0, seg.v1, i * slot + slotPad, innerW)
                  return (
                    <rect key={`${sr.id}-${i}`} {...r} {...barStyle(sr.metric, sr.estimated)} />
                  )
                }),
              )}
            {/* Zero line drawn over the bars so a negative bar visibly hangs
                from it; stronger than the grid when the scale spans zero. */}
            <line
              x1={0}
              x2={SVG_W}
              y1={zeroY}
              y2={zeroY}
              stroke={hasNegative ? CHART_ZERO_COLOR : CHART_GRID_COLOR}
              strokeWidth={hasNegative ? 1.5 : 1}
              vectorEffect="non-scaling-stroke"
            />
          </svg>

          {hover != null && hoverPct != null && (
            <div
              dir={dirFor(lang)}
              className="absolute top-0 z-10 pointer-events-none rounded-lg px-3 py-2 text-xs shadow-md"
              style={{
                left: `${hoverPct}%`,
                transform: hoverPct < 25 ? 'none' : hoverPct > 75 ? 'translateX(-100%)' : 'translateX(-50%)',
                background: CHART_TOOLTIP_BG,
                border: `1px solid ${CHART_TOOLTIP_BORDER}`,
              }}
            >
              <div className="font-semibold text-[var(--text-primary)] mb-1">{labels[hover]}</div>
              {series.map((sr) => {
                const v = sr.values[hover]
                if (v == null || !Number.isFinite(v)) return null
                return (
                  <div key={sr.id} className="flex items-center gap-1.5 whitespace-nowrap text-[var(--text-secondary)]">
                    <span
                      className="inline-block w-2 h-2 rounded-sm shrink-0"
                      style={{ background: metricColor(sr.metric) }}
                    />
                    <span>
                      {sr.label}
                      {sr.estimated ? s.estimatedSuffix : ''}:
                    </span>
                    <span className="font-medium text-[var(--text-primary)]">{fmtValue(v)}</span>
                  </div>
                )
              })}
            </div>
          )}

          <div className="relative h-4 mt-1">
            {xTicks.map((i) => (
              <span
                key={i}
                className="absolute text-[10px] text-[var(--text-muted)] whitespace-nowrap"
                style={{
                  left: `${((i * slot + slot / 2) / SVG_W) * 100}%`,
                  transform: i === 0 ? 'none' : i === count - 1 ? 'translateX(-100%)' : 'translateX(-50%)',
                }}
              >
                {labels[i]}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
