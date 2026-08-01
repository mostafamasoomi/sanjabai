import { Reveal } from './Reveal'
import { STATS } from './content'

/**
 * A definition list: the label defines the number. DOM order is dt → dd for
 * semantics, and `.lp-stat` uses column-reverse so the number still reads on
 * top visually.
 *
 * Each stat gets its own staggered "flap" reveal (`lp-flip`, a steeper
 * rotateX than the site's default unfold — see landing.css) rather than one
 * flat fade for the whole row: a few of these values aren't numbers at all
 * ("تومان"), so an odometer-style count-up would only ever apply to half of
 * them and read as inconsistent. A sequential flap-down lands the same way
 * for every value regardless of what it says.
 */
export function StatsBand() {
  return (
    <dl className="lp-stats">
      {STATS.map((stat, i) => (
        <Reveal key={stat.label} as="div" delay={i * 110} className="lp-stat lp-flip">
          <dt className="lp-stat__label">{stat.label}</dt>
          <dd className="lp-stat__value lp-num">{stat.value}</dd>
        </Reveal>
      ))}
    </dl>
  )
}
