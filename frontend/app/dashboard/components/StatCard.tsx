import { Icon, type IconName } from '@/components/ui/Icon'
import { Num } from '@/lib/format'

/* ═══════════════════════════════════════════════════════════════
   Stat Card
   ═══════════════════════════════════════════════════════════════ */

export function StatCard({
  icon,
  label,
  value,
  unit,
  lead = false,
}: {
  icon: IconName
  label: string
  value: number
  unit?: string
  /** The one card on the page allowed the top step of the type scale. */
  lead?: boolean
}) {
  return (
    <div className={`card stat-card${lead ? ' stat-card--lead' : ''}`}>
      <div className="stat-card__head">
        <span className="stat-card__label">{label}</span>
        <div className="stat-card__icon">
          <Icon name={icon} size={16} />
        </div>
      </div>
      <Num className="stat-card__value" value={value} />
      {unit && <div className="stat-card__unit">{unit}</div>}
    </div>
  )
}
