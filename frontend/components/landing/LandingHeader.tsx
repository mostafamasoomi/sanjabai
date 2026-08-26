'use client'

import { useEffect, useState } from 'react'
import { Icon } from '../ui/Icon'
import { LanguageToggle, useLang } from '../LanguageToggle'
import { ThemeToggle } from '../ThemeToggle'
import { BrandMark } from './primitives'
import { navContent } from './content'
import { landingHeaderStrings } from './LandingHeader.strings'

export function LandingHeader() {
  const lang = useLang()
  const s = landingHeaderStrings(lang)
  const { links } = navContent(lang)
  const [scrolled, setScrolled] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // While the drawer covers the page, freeze the document behind it and let
  // Escape close it — the previous header simply hid its links under 640px,
  // which left phones with no navigation at all.
  useEffect(() => {
    if (!menuOpen) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = previous
      document.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  return (
    <>
      <header className="lp-header" data-scrolled={scrolled}>
        <div className="lp-container lp-header__inner">
          <a href="/" className="lp-brand">
            <BrandMark />
          </a>

          <nav className="lp-nav" aria-label={s.navAria}>
            {links.map((link) => (
              <a key={link.href} href={link.href} className="lp-nav__link">
                {link.label}
              </a>
            ))}
          </nav>

          <div className="lp-header__actions">
            <ThemeToggle />
            <LanguageToggle />
            <a href="/login" className="lp-nav__link">
              {s.signIn}
            </a>
            <a href="/signup" className="lp-btn lp-btn--primary">
              {s.signUp}
            </a>
            <button
              type="button"
              className="lp-icon-btn lp-burger"
              aria-label={s.openMenuAria}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen(true)}
            >
              <Icon name="menu" size={22} />
            </button>
          </div>
        </div>
      </header>

      {menuOpen && (
        <div className="lp-drawer" role="dialog" aria-modal="true" aria-label={s.menuDialogAria}>
          <div className="lp-drawer__top">
            <a href="/" className="lp-brand" onClick={() => setMenuOpen(false)}>
              <BrandMark />
            </a>
            <button
              type="button"
              className="lp-icon-btn"
              aria-label={s.closeMenuAria}
              onClick={() => setMenuOpen(false)}
            >
              <Icon name="close" size={22} />
            </button>
          </div>

          <div className="lp-drawer__body">
            {links.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="lp-drawer__link"
                onClick={() => setMenuOpen(false)}
              >
                {link.label}
              </a>
            ))}

            <div className="lp-drawer__actions">
              <a href="/signup" className="lp-btn lp-btn--primary lp-btn--lg lp-btn--block">
                {s.signUp}
              </a>
              <a href="/login" className="lp-btn lp-btn--secondary lp-btn--lg lp-btn--block">
                {s.drawerSignIn}
              </a>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
