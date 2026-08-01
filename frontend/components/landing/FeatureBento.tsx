import { Icon } from '../ui/Icon'
import { Reveal } from './Reveal'
import { ForwardArrow } from './primitives'
import { FEATURES } from './content'

export function FeatureBento() {
  return (
    <section id="features" className="lp-section">
      <div className="lp-container">
        <Reveal>
          <header className="lp-head">
            <span className="lp-eyebrow">امکانات</span>
            <h2 className="lp-title">هر چه لازم دارید، بدون اضافه‌کاری</h2>
            <p className="lp-lead">
              یک فضای کاری برای همه‌ی مدل‌ها: چت، ساخت عامل، مقایسه‌ی خروجی و مدیریت کلیدهای
              API — همه در یک جا و با یک صورتحساب.
            </p>
          </header>
        </Reveal>

        <div className="lp-bento">
          {FEATURES.map((feature, i) => {
            const isWide = i === FEATURES.length - 1
            return (
              <Reveal
                key={feature.title}
                as="article"
                delay={i * 60}
                // The wide closer tile is ~117px tall and spans the full
                // row — a rotateY tilt on something that short and wide is
                // geometrically almost imperceptible, so it isn't worth the
                // pointer listener. The three square-ish tiles above it are
                // where tilt actually reads.
                tilt={!isWide}
                className={`lp-card lp-feature${isWide ? ' lp-feature--wide' : ''}`}
              >
                <span className="lp-feature__icon">
                  <Icon name={feature.icon} size={20} />
                </span>
                <h3 className="lp-feature__title">{feature.title}</h3>
                <p className="lp-feature__desc">{feature.desc}</p>
                {feature.href && (
                  <a href={feature.href} className="lp-feature__link">
                    {feature.linkLabel}
                    <ForwardArrow size={13} />
                  </a>
                )}
              </Reveal>
            )
          })}
        </div>
      </div>
    </section>
  )
}
