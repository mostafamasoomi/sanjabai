'use client'

import { useLang } from '../LanguageToggle'
import { Reveal } from './Reveal'
import { stepsContent } from './content'
import { howItWorksStrings } from './HowItWorks.strings'

export function HowItWorks() {
  const lang = useLang()
  const s = howItWorksStrings(lang)
  const { items } = stepsContent(lang)

  return (
    <section className="lp-section lp-section--soft">
      <div className="lp-container">
        <Reveal>
          <header className="lp-head">
            <span className="lp-eyebrow">{s.eyebrow}</span>
            <h2 className="lp-title">{s.title}</h2>
          </header>
        </Reveal>

        <ol className="lp-steps">
          {items.map((step, i) => (
            <Reveal key={step.title} as="li" className="lp-step" delay={i * 90}>
              <h3 className="lp-step__title">{step.title}</h3>
              <p className="lp-step__desc">{step.desc}</p>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  )
}
