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
  buildSharedPoints,
  indexToX,
  isEmptySeries,
  niceScale,
  seriesExtent,
  tickIndices,
  valueToY,
  type ChartSeries,
  type PlotBox,
} from './chartUtils'

/* ═══════════════════════════════════════════════════════════════════════════
   Multi-series line chart, hand-written SVG — recharts is BANNED (breaks the
   build, see ../AdminCharts.tsx). Follows the established pattern
   (MonitoringCharts.tsx, AnalyticsSection.tsx): the numeric plot lives inside
   a `dir="ltr"` wrapper so the x axis reads oldest→newest left-to-right even
   though the panel is RTL, while the legend and tooltip text stay in the
   language's own direction. All series share ONE y scale (chartUtils) so a
   series near zero visibly looks near zero. Negative values are first-class:
   when the scale spans zero, a stronger zero line is drawn and lines dip
   below it. A series flagged `estimated` renders dashed and its label carries
   the «(تخمینی)» suffix — derived data must never read as measured.
   ═══════════════════════════════════════════════════════════════════════════ */

export interface LineChartSeries extends ChartSeries {
  metric: ChartMetric
}

export interface LineChartProps {
  /** Category labels aligned by index with every series' values — already
   *  display-ready (the caller localizes dates; see dayLabel in
   *  AnalyticsSection.tsx for the idiom). */
  labels: string[]
  series: LineChartSeries[]
  /** Accessible description of the whole chart (required — an unlabeled
   *  role="img" is worse than none). */
  ariaLabel: string
  /** Tooltip value formatter. Money charts pass fmt(lang).price — values are
   *  raw integer tomans and are never rescaled here. Defaults to fmt.num. */
  formatValue?: (v: number) => string
  /** Y-axis tick formatter; defaults to fmt.compact so million-toman ticks
   *  fit the gutter. */
  formatTick?: (v: number) => string
  height?: number
  maxXTicks?: number
}

const SVG_W = 600
const Y_AXIS_WIDTH = '4rem'

export default function LineChart({
  labels,
  series,
  ariaLabel,
  formatValue,
  formatTick,
  height = 160,
  maxXTicks = 7,
}: LineChartProps) {
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
  const scale = useMemo(() => niceScale(seriesExtent(series)), [series])
  const segmentsBySeries = useMemo(
    () => series.map((sr) => buildSharedPoints(sr.values, scale, box)),
    [series, scale, box],
  )

  if (isEmptySeries(labels, series)) {
    return <div className="text-center text-[var(--text-muted)] py-8 text-sm">{s.empty}</div>
  }

  const count = labels.length
  const hasNegative = scale.min < 0
  const zeroY = valueToY(0, scale, box)
  const xTicks = tickIndices(count, maxXTicks)

  const onMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    if (rect.width === 0) return
    const frac = (e.clientX - rect.left) / rect.width
    const i = Math.round(frac * (count - 1))
    setHover(Math.max(0, Math.min(count - 1, i)))
  }

  const hoverX = hover != null ? indexToX(hover, count, box) : null
  const hoverPct = hoverX != null ? (hoverX / SVG_W) * 100 : null

  return (
    <div>
      {/* Legend — stays in the surrounding RTL flow. */}
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

      {/* Plot — LTR so the numeric axes are not mirrored by the RTL panel. */}
      <div dir="ltr" className="flex">
        {/* Y-axis gutter */}
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

        {/* Plot area + hover layer */}
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
            {hasNegative && (
              <line
                x1={0}
                x2={SVG_W}
                y1={zeroY}
                y2={zeroY}
                stroke={CHART_ZERO_COLOR}
                strokeWidth={1.5}
                vectorEffect="non-scaling-stroke"
              />
            )}
            {hoverX != null && (
              <line
                x1={hoverX}
                x2={hoverX}
                y1={0}
                y2={height}
                stroke={CHART_GRID_COLOR}
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
            )}
            {series.map((sr, i) =>
              segmentsBySeries[i].map((points, j) => (
                <polyline
                  key={`${sr.id}-${j}`}
                  points={points}
                  fill="none"
                  stroke={metricColor(sr.metric)}
                  strokeWidth={2}
                  strokeDasharray={sr.estimated ? '6 4' : undefined}
                  vectorEffect="non-scaling-stroke"
                />
              )),
            )}
            {hover != null &&
              series.map((sr) => {
                const v = sr.values[hover]
                if (v == null || !Number.isFinite(v)) return null
                return (
                  <circle
                    key={`dot-${sr.id}`}
                    cx={indexToX(hover, count, box)}
                    cy={valueToY(v, scale, box)}
                    r={3}
                    fill={metricColor(sr.metric)}
                  />
                )
              })}
          </svg>

          {/* Tooltip */}
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

          {/* X-axis labels, thinned — inside the LTR wrapper on purpose so
              the oldest label sits under the oldest point (left). */}
          <div className="relative h-4 mt-1">
            {xTicks.map((i) => (
              <span
                key={i}
                className="absolute text-[10px] text-[var(--text-muted)] whitespace-nowrap"
                style={{
                  left: `${(indexToX(i, count, box) / SVG_W) * 100}%`,
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
