'use client'

import { useLang } from '../LanguageToggle'
import { CheckGlyph } from './primitives'
import { comparisonContent } from './content'
import { comparisonSectionStrings } from './ComparisonSection.strings'

/**
 * Restates claims already established elsewhere on the page (stats,
 * pricing, hero trust list, FAQ) side-by-side with the general pattern
 * subscription services share — see the header comment on comparisonContent
 * in content/comparison.ts for why the right column stays unnamed and
 * unquantified.
 */
export function ComparisonSection() {
  const lang = useLang()
  const s = comparisonSectionStrings(lang)
  const { rows } = comparisonContent(lang)

  return (
    <section className="lp-section lp-section--soft" id="comparison">
      <div className="lp-container">
        <header className="lp-head">
          <span className="lp-eyebrow">{s.eyebrow}</span>
          <h2 className="lp-title">{s.title}</h2>
          <p className="lp-lead">{s.lead}</p>
        </header>

        {/* The table is wider than a phone screen (3 columns of real content
            don't fit in ~350px) — .lp-compare scrolls horizontally, but a
            scroll affordance nobody notices is the same as no affordance, so
            this is a plain-text hint rather than a subtle edge gradient. Only
            shown under the breakpoint where scrolling is actually needed. */}
        <p className="lp-compare__hint">{s.scrollHint}</p>

        <div className="lp-compare">
          <table className="lp-compare__table">
            <thead>
              <tr>
                <th scope="col" />
                <th scope="col" className="lp-compare__col--brand">
                  <span dir="ltr">Sanjabai</span>
                </th>
                <th scope="col">{s.subscriptionColumnHeading}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label}>
                  <th scope="row">{row.label}</th>
                  <td className="lp-compare__col--brand">
                    <span className="lp-compare__value">
                      <CheckGlyph size={14} />
                      {row.sanjabai}
                    </span>
                  </td>
                  <td>{row.subscription}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
