/* ═══════════════════════════════════════════════════════════════════════════
   Donut chart (pure SVG, no library)
   Split out of page.tsx verbatim -- no behaviour change.
   ═══════════════════════════════════════════════════════════════════════════ */

export function DonutChart({
  data,
  size = 200,
  thickness = 26,
  centerLabel,
  centerValue,
}: {
  data: { label: string; value: number; color: string }[]
  size?: number
  thickness?: number
  centerLabel?: string
  centerValue?: string
}) {
  const radius = (size - thickness) / 2
  const circumference = 2 * Math.PI * radius
  const total = data.reduce((s, d) => s + d.value, 0) || 1
  let offset = 0
  return (
    <div style={{ position: 'relative', width: size, height: size, margin: '0 auto' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }} aria-hidden>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--border)"
          strokeWidth={thickness}
        />
        {data.map((d, i) => {
          const frac = d.value / total
          const len = frac * circumference
          const seg = (
            <circle
              key={i}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={d.color}
              strokeWidth={thickness}
              strokeDasharray={`${len} ${circumference - len}`}
              strokeDashoffset={-offset}
              strokeLinecap="butt"
              style={{ transition: 'stroke-dasharray 0.6s ease, stroke-dashoffset 0.6s ease' }}
            />
          )
          offset += len
          return seg
        })}
      </svg>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 2,
        }}
      >
        {centerValue && (
          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', fontFeatureSettings: '"tnum"' }}>
            {centerValue}
          </div>
        )}
        {centerLabel && (
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{centerLabel}</div>
        )}
      </div>
    </div>
  )
}
