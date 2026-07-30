/* ═══════════════════════════════════════════════════════════════════════════
   Small shared pieces used across landing sections.
   ═══════════════════════════════════════════════════════════════════════════ */

const FA_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']

/**
 * Formats a number for Persian readers: thousands separators plus Persian
 * digits. `toLocaleString('fa-IR')` would do this too, but it depends on the
 * runtime's ICU data — which differs between the Node server and the browser
 * and produced hydration mismatches. This is deterministic on both sides.
 */
export function faNumber(value: number): string {
  const grouped = Math.round(value)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, '٬')
  return grouped.replace(/\d/g, (d) => FA_DIGITS[Number(d)])
}

/**
 * Provider brand mark. Rendered as a CSS mask rather than an <img> because the
 * source SVGs in /public/ai carry inconsistent fills — some are hard-coded
 * #ffffff, others have none and default to black, so half of them vanished
 * against a dark background. A mask ignores the fill entirely and paints with
 * `currentColor`, which also makes the marks theme-aware for free.
 */
export function ProviderLogo({ src, size }: { src: string; size?: number }) {
  return (
    <span
      className="lp-logo"
      aria-hidden="true"
      style={
        {
          '--lp-logo-src': `url("${src}")`,
          ...(size ? { '--lp-logo-size': `${size}px` } : null),
        } as React.CSSProperties
      }
    />
  )
}

/* ── Inline glyphs ────────────────────────────────────────────────────────── */

export function CheckGlyph({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M3 8.5 6.2 11.5 13 4.5"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function ChevronGlyph({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="m4 6 4 4 4-4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * Chevron that points along the reading direction. In an RTL document "next"
 * is to the left, so the glyph is mirrored by CSS rather than being swapped
 * for a different path.
 */
export function ForwardArrow({ size = 15 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      className="lp-btn__arrow"
    >
      <path
        d="M3 8h9m0 0L8.5 4.5M12 8l-3.5 3.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** The product mark, used in the header and the footer. */
export function BrandMark() {
  // eslint-disable-next-line @next/next/no-img-element -- a fixed-size SVG;
  // next/image would add a loader and layout wrapper for no benefit.
  return <img src="/logo.svg" alt="" width={28} height={28} className="lp-brand__mark" />
}
