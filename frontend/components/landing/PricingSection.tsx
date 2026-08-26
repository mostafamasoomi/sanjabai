'use client'

import { useLang } from '../LanguageToggle'
import { Reveal } from './Reveal'
import { CheckGlyph, ForwardArrow } from './primitives'
import { pricingContent } from './content'
import { pricingSectionStrings } from './PricingSection.strings'

/**
 * Sanjabai bills per token against a prepaid wallet — see app/pricing/page.tsx.
 * These columns explain that model rather than inventing subscription tiers,
 * so this section can't end up contradicting the real pricing page. The
 * per-model rate table lives on /pricing; this just links there.
 */
export function PricingSection() {
  const lang = useLang()
  const s = pricingSectionStrings(lang)
  const { columns } = pricingContent(lang)

  return (
    <section id="pricing" className="lp-section lp-section--soft">
      <div className="lp-container">
        <Reveal>
          <header className="lp-head">
            <span className="lp-eyebrow">{s.eyebrow}</span>
            <h2 className="lp-title">{s.title}</h2>
            <p className="lp-lead">{s.lead}</p>
          </header>
        </Reveal>

        <div className="lp-plans">
          {columns.map((column, i) => (
            <Reveal
              key={column.name}
              as="article"
              delay={i * 90}
              tilt
              tiltDeg={4}
              className={`lp-card lp-plan${column.featured ? ' lp-plan--featured' : ''}`}
            >
              {column.featured && <span className="lp-plan__badge">{s.featuredBadge}</span>}

              <h3 className="lp-plan__name">{column.name}</h3>
              <p className="lp-plan__desc">{column.desc}</p>

              <p className="lp-plan__price">
                <span className="lp-plan__amount">{column.headline}</span>
                {column.headlineNote && (
                  <span className="lp-plan__unit">{column.headlineNote}</span>
                )}
              </p>

              <ul className="lp-plan__features">
                {column.features.map((feature) => (
                  <li key={feature}>
                    <CheckGlyph />
                    {feature}
                  </li>
                ))}
              </ul>

              <a
                href={column.href}
                className={`lp-btn lp-btn--block ${
                  column.featured ? 'lp-btn--primary' : 'lp-btn--secondary'
                }`}
              >
                {column.cta}
              </a>
            </Reveal>
          ))}
        </div>

        <Reveal delay={180}>
          <p className="lp-plans__footnote">
            <a href="/pricing" className="lp-feature__link">
              {s.fullRateLink}
              <ForwardArrow size={13} />
            </a>
          </p>
        </Reveal>
      </div>
    </section>
  )
}
