import { Reveal } from './Reveal'
import { CheckGlyph, ForwardArrow } from './primitives'
import { PRICING_COLUMNS } from './content'

/**
 * Sanjhubai bills per token against a prepaid wallet — see app/pricing/page.tsx.
 * These columns explain that model rather than inventing subscription tiers,
 * so this section can't end up contradicting the real pricing page. The
 * per-model rate table lives on /pricing; this just links there.
 */
export function PricingSection() {
  return (
    <section id="pricing" className="lp-section lp-section--soft">
      <div className="lp-container">
        <Reveal>
          <header className="lp-head">
            <span className="lp-eyebrow">تعرفه‌ها</span>
            <h2 className="lp-title">فقط بابت آنچه مصرف می‌کنید بپردازید</h2>
            <p className="lp-lead">
              اشتراک ماهانه‌ای در کار نیست. کیف پولتان را به تومان شارژ می‌کنید و هزینه‌ی هر
              درخواست به‌ازای توکن از همان کسر می‌شود.
            </p>
          </header>
        </Reveal>

        <div className="lp-plans">
          {PRICING_COLUMNS.map((column, i) => (
            <Reveal
              key={column.name}
              as="article"
              delay={i * 90}
              tilt
              tiltDeg={4}
              className={`lp-card lp-plan${column.featured ? ' lp-plan--featured' : ''}`}
            >
              {column.featured && <span className="lp-plan__badge">روش اصلی</span>}

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
              مشاهده‌ی تعرفه‌ی دقیق هر مدل
              <ForwardArrow size={13} />
            </a>
          </p>
        </Reveal>
      </div>
    </section>
  )
}
