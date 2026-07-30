import { Reveal } from './Reveal'
import { STEPS } from './content'

export function HowItWorks() {
  return (
    <section className="lp-section lp-section--soft">
      <div className="lp-container">
        <Reveal>
          <header className="lp-head">
            <span className="lp-eyebrow">شروع کار</span>
            <h2 className="lp-title">در سه قدم راه بیفتید</h2>
          </header>
        </Reveal>

        <ol className="lp-steps">
          {STEPS.map((step, i) => (
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
