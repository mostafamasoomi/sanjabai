import { ProviderLogo } from './primitives'
import { PROVIDERS } from './content'

function Track({ ariaHidden = false }: { ariaHidden?: boolean }) {
  return (
    <div className="lp-marquee__track" aria-hidden={ariaHidden || undefined}>
      {PROVIDERS.map((p) => (
        <span key={p.name} className="lp-marquee__item">
          <ProviderLogo src={p.logo} />
          <span dir="ltr">{p.name}</span>
        </span>
      ))}
    </div>
  )
}

/**
 * Continuous logo strip. Two identical tracks sit side by side and translate
 * by a full width, so the second slides into place exactly as the first
 * leaves — no seam and no JS. The duplicate is hidden from assistive tech.
 */
export function ProviderMarquee() {
  return (
    <div className="lp-marquee">
      <p className="lp-marquee__label">دسترسی مستقیم به مدل‌های</p>
      <div className="lp-marquee__viewport">
        <Track />
        <Track ariaHidden />
      </div>
    </div>
  )
}
