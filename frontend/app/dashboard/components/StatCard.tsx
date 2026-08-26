'use client'

import { Icon, type IconName } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'

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
  const lang = useLang()
  const f = fmt(lang)

  return (
    <div className={`card stat-card${lead ? ' stat-card--lead' : ''}`}>
      <div className="stat-card__head">
        <span className="stat-card__label">{label}</span>
        <div className="stat-card__icon">
          <Icon name={icon} size={16} />
        </div>
      </div>
      {/* Plain span rather than <Num> -- <Num> always renders Persian digits
          (lib/format's faNum), which would be wrong in the English UI. */}
      <span className="num stat-card__value">{f.num(value)}</span>
      {unit && <div className="stat-card__unit">{unit}</div>}
    </div>
  )
}
