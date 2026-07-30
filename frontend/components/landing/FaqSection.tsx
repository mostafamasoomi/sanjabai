'use client'

import { useId, useState } from 'react'
import { Reveal } from './Reveal'
import { ChevronGlyph } from './primitives'
import { FAQ } from './content'

export function FaqSection() {
  // Accordion, not a disclosure set: at most one answer open at a time.
  const [open, setOpen] = useState<number | null>(0)
  const baseId = useId()

  return (
    <section className="lp-section">
      <div className="lp-container">
        <Reveal>
          <header className="lp-head">
            <span className="lp-eyebrow">سوالات متداول</span>
            <h2 className="lp-title">چیزهایی که معمولاً می‌پرسند</h2>
          </header>
        </Reveal>

        <Reveal>
          <div className="lp-faq">
            {FAQ.map((item, i) => {
              const expanded = open === i
              const panelId = `${baseId}-panel-${i}`
              const triggerId = `${baseId}-trigger-${i}`

              return (
                <div key={item.q} className="lp-faq__item">
                  <h3 className="lp-faq__heading">
                    <button
                      type="button"
                      id={triggerId}
                      className="lp-faq__trigger"
                      aria-expanded={expanded}
                      aria-controls={panelId}
                      onClick={() => setOpen(expanded ? null : i)}
                    >
                      {item.q}
                      <span className="lp-faq__chevron">
                        <ChevronGlyph />
                      </span>
                    </button>
                  </h3>

                  {/* The answer stays mounted whether or not it is open, so it
                      remains findable by in-page search and by crawlers; the
                      collapse is a grid-rows transition, not an unmount. */}
                  <div
                    id={panelId}
                    role="region"
                    aria-labelledby={triggerId}
                    className="lp-faq__panel"
                    data-open={expanded}
                  >
                    <div>
                      <p className="lp-faq__answer">{item.a}</p>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </Reveal>
      </div>
    </section>
  )
}
