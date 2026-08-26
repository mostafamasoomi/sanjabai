'use client'

import { useLang } from '../LanguageToggle'
import { Reveal } from './Reveal'
import { ForwardArrow } from './primitives'
import { closingCtaStrings } from './ClosingCta.strings'

export function ClosingCta() {
  const lang = useLang()
  const s = closingCtaStrings(lang)

  return (
    <section className="lp-section">
      <div className="lp-container">
        <Reveal className="lp-cta">
          <h2 className="lp-title">{s.title}</h2>
          <p className="lp-lead">{s.lead}</p>
          <div className="lp-hero__actions">
            <a href="/signup" className="lp-btn lp-btn--primary lp-btn--lg">
              {s.signupCta}
              <ForwardArrow />
            </a>
            <a href="/developer" className="lp-btn lp-btn--ghost lp-btn--lg">
              {s.docsCta}
            </a>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
