/* The full squirrel + wordmark lockup, in the one place that knows how to
   pick the right file for the current theme.

   TWO FILES, NOT ONE. The source artwork paints the wordmark with a
   `charcoal` gradient (#171B1F -> #080B0E). That is correct on cream and
   invisible on the dark theme's #0e0906 page, so `logo-lockup-dark.svg` is
   the same artwork with those two stops swapped for the theme's own ink
   (#F6EFE2 -> #D8CBB6). The squirrel's copper gradient is identical in both
   and already matches --lp-brand exactly.

   THE TAGLINE IS DELIBERATELY GONE. The delivered lockup is 1961x802 and
   carries "Intelligence, Gathered." under the wordmark; at the ~32px height
   a header gives it that line renders about three pixels tall, which is
   noise rather than a tagline. Both files are cropped to viewBox
   "63 85 1850 538" -- the squirrel+wordmark band, measured with getBBox in
   a real browser, not eyeballed. Aspect is 3.44:1, so callers set a height
   and the width follows.

   Swapped in CSS rather than by reading the theme in JS: the theme lives in
   a `data-theme` attribute on <html> that is already set before paint, so a
   CSS swap has no hydration mismatch and no flash of the wrong mark.

   Two <img> tags rather than one inlined SVG on purpose -- both files
   define `id="charcoal"`, and inlining both into one document would let the
   first shadow the second. As separate image documents they cannot collide.
   (Verified: rendering both inline in one page really does paint the dark
   variant with the light variant's gradient.) */
export function BrandLockup({ height = 30, className = '' }: { height?: number; className?: string }) {
  return (
    <span
      className={`brand-lockup${className ? ' ' + className : ''}`}
      style={{ height }}
      role="img"
      aria-label="Sanjabai"
    >
      {/* eslint-disable @next/next/no-img-element -- fixed-aspect SVGs; next/image
          would add a loader and a layout wrapper for no benefit. */}
      <img src="/logo-lockup-dark.svg" alt="" aria-hidden="true" className="brand-lockup__img brand-lockup__img--dark" />
      <img src="/logo-lockup.svg" alt="" aria-hidden="true" className="brand-lockup__img brand-lockup__img--light" />
    </span>
  )
}
