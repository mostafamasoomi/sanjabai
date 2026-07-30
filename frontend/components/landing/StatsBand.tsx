import { Reveal } from './Reveal'
import { STATS } from './content'

/**
 * A definition list: the label defines the number. DOM order is dt → dd for
 * semantics, and `.lp-stat` uses column-reverse so the number still reads on
 * top visually.
 */
export function StatsBand() {
  return (
    <Reveal>
      <dl className="lp-stats">
        {STATS.map((stat) => (
          <div key={stat.label} className="lp-stat">
            <dt className="lp-stat__label">{stat.label}</dt>
            <dd className="lp-stat__value lp-num">{stat.value}</dd>
          </div>
        ))}
      </dl>
    </Reveal>
  )
}
