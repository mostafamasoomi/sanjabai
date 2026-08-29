'use client'

import { useLang } from '../LanguageToggle'
import { toFaDigits } from '@/lib/format'
import { BrandMark } from './primitives'
import { EnamadBadge } from './EnamadBadge'
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
            <EnamadBadge compact />
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
        </div>
      </div>
    </footer>
  )
}
