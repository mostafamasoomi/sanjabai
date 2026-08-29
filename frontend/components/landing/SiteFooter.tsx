'use client'

import { useLang } from '../LanguageToggle'
import { toFaDigits } from '@/lib/format'
import { BrandMark } from './primitives'
import { footerContent } from './content'
import { siteFooterStrings } from './SiteFooter.strings'

export function SiteFooter() {
  const lang = useLang()
  const s = siteFooterStrings(lang)
  const { columns } = footerContent(lang)
  // Persian goes through Intl for the calendar conversion and then through
  // toFaDigits, because the production Node image is built with small-icu and
  // returns Latin digits from a fa-IR format (the reason lib/format.tsx
  // normalises every Intl result it produces).
  const now = new Date()
  const year = lang === 'en'
    ? String(now.getFullYear())
    : toFaDigits(now.toLocaleDateString('fa-IR', { year: 'numeric' }))

  return (
    <footer className="lp-footer">
      <div className="lp-container">
        <div className="lp-footer__top">
          <div className="lp-footer__about">
            <a href="/" className="lp-brand">
              <BrandMark />
            </a>
            <p className="lp-footer__tagline">{s.tagline}</p>
          </div>

          {columns.map((column) => (
            <nav key={column.title} className="lp-footer__col" aria-label={column.title}>
              <h3>{column.title}</h3>
              {column.links.map((link) => (
                <a key={link.href} href={link.href}>
                  {link.label}
                </a>
              ))}
            </nav>
          ))}
        </div>

        <div className="lp-footer__bottom">
          <span>{s.copyright(year)}</span>
          <span>{s.madeFor}</span>
          {/* eNamad trust seal. Markup is exactly what enamad.ir's badge
              generator issues for this site's id/Code — kept verbatim via
              dangerouslySetInnerHTML (including the nonstandard `code`
              attribute on <img>) rather than hand-converted to JSX, since
              enamad's own verification may depend on the exact markup. */}
          <span
            className="lp-footer__enamad"
            dangerouslySetInnerHTML={{
              __html:
                "<a referrerpolicy='origin' target='_blank' href='https://trustseal.enamad.ir/?id=7527649&Code=438FIkEWAO3ftUDcIFWbdnA9GyyRducv'><img referrerpolicy='origin' src='https://trustseal.enamad.ir/logo.aspx?id=7527649&Code=438FIkEWAO3ftUDcIFWbdnA9GyyRducv' alt='' style='cursor:pointer' code='438FIkEWAO3ftUDcIFWbdnA9GyyRducv'></a>",
            }}
          />
        </div>
      </div>
    </footer>
  )
}
