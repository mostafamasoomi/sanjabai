import { ProviderLogo } from './primitives'
import { CATALOG } from './content'

function Track({ ariaHidden = false }: { ariaHidden?: boolean }) {
  return (
    <div className="lp-marquee__track" aria-hidden={ariaHidden || undefined}>
      {CATALOG.map((model) => (
        <span key={model.name} className="lp-marquee__item">
          {/* Vendors without a mark in /public/ai render as a name alone —
              better than borrowing a logo that isn't theirs. */}
          {'logo' in model && model.logo && <ProviderLogo src={model.logo} />}
          <span dir="ltr">{model.name}</span>
        </span>
      ))}
    </div>
  )
}

/**
 * Continuous strip of the real catalog (backend/litellm_config.yaml). Two
 * identical tracks sit side by side and translate by a full width, so the
 * second slides into place exactly as the first leaves — no seam and no JS.
 * The duplicate is hidden from assistive tech.
 */
export function ProviderMarquee() {
  return (
    <div className="lp-marquee">
      <p className="lp-marquee__label">۲۳ مدل، از یک پنل</p>
      <div className="lp-marquee__viewport">
        <Track />
        <Track ariaHidden />
      </div>
    </div>
  )
}
