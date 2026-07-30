'use client'

import { useState } from 'react'
import { Reveal } from './Reveal'
import { CheckGlyph, faNumber } from './primitives'
import { PLANS, type Plan } from './content'

type Cycle = 'monthly' | 'yearly'

function priceOf(plan: Plan, cycle: Cycle) {
  const amount = cycle === 'monthly' ? plan.monthly : plan.yearly
  if (amount === null) return { amount: 'تماس بگیرید', unit: '' }
  if (amount === 0) return { amount: 'رایگان', unit: 'برای همیشه' }
  return {
    amount: faNumber(amount),
    unit: cycle === 'monthly' ? 'تومان / ماه' : 'تومان / سال',
  }
}

export function PricingSection() {
  const [cycle, setCycle] = useState<Cycle>('monthly')

  return (
    <section id="pricing" className="lp-section lp-section--soft">
      <div className="lp-container">
        <Reveal>
          <header className="lp-head">
            <span className="lp-eyebrow">تعرفه‌ها</span>
            <h2 className="lp-title">قیمت‌گذاری ساده و شفاف</h2>
            <p className="lp-lead">
              رایگان شروع کنید و فقط وقتی ارتقا دهید که واقعاً به آن نیاز داشتید. همه‌ی
              مبالغ به تومان و شامل مالیات است.
            </p>

            <div className="lp-billing" role="group" aria-label="دوره‌ی پرداخت">
              <button
                type="button"
                className="lp-billing__opt"
                aria-pressed={cycle === 'monthly'}
                onClick={() => setCycle('monthly')}
              >
                ماهانه
              </button>
              <button
                type="button"
                className="lp-billing__opt"
                aria-pressed={cycle === 'yearly'}
                onClick={() => setCycle('yearly')}
              >
                سالانه
                <span className="lp-billing__save">۲۵٪ تخفیف</span>
              </button>
            </div>
          </header>
        </Reveal>

        <div className="lp-plans">
          {PLANS.map((plan, i) => {
            const price = priceOf(plan, cycle)
            return (
              <Reveal
                key={plan.name}
                as="article"
                delay={i * 90}
                className={`lp-card lp-plan${plan.featured ? ' lp-plan--featured' : ''}`}
              >
                {plan.featured && <span className="lp-plan__badge">محبوب‌ترین</span>}

                <h3 className="lp-plan__name">{plan.name}</h3>
                <p className="lp-plan__desc">{plan.desc}</p>

                <p className="lp-plan__price">
                  <span className="lp-plan__amount lp-num">{price.amount}</span>
                  {price.unit && <span className="lp-plan__unit">{price.unit}</span>}
                </p>

                <ul className="lp-plan__features">
                  {plan.features.map((feature) => (
                    <li key={feature}>
                      <CheckGlyph />
                      {feature}
                    </li>
                  ))}
                </ul>

                <a
                  href={plan.href}
                  className={`lp-btn lp-btn--block ${
                    plan.featured ? 'lp-btn--primary' : 'lp-btn--secondary'
                  }`}
                >
                  {plan.cta}
                </a>
              </Reveal>
            )
          })}
        </div>
      </div>
    </section>
  )
}
