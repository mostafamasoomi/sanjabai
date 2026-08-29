'use client'

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { Icon, type IconName } from '../ui/Icon'
import { dirFor } from '@/lib/i18n'
import type { Lang } from '../LanguageToggle'

/* ═══════════════════════════════════════════════════════════════════════════
   SpotlightOverlay — the anchored coach-mark tour's visual layer.

   Two pieces, both here so ProductTour.tsx's CenteredStep (the welcome step
   and the "element never appeared" fallback) can reuse the exact same header
   and footer instead of a second copy: `TourHeader` (progress dots / step
   counter / close) and `TourFooter` (prev / next / skip / finish) are plain
   presentational exports, `TourBody` renders the chapter/title/combo/body/CTA
   block. `SpotlightOverlay` composes all three around a live target rect.

   Cutout: NOT an SVG mask. One `position:fixed` box sized to the target rect
   + a small padding, with `box-shadow: 0 0 0 200vmax rgba(0,0,0,.6)` — the
   shadow's absurd spread radius IS the dimmed backdrop, the box itself is the
   "hole". `transition: all 250ms` makes it morph smoothly between two anchors
   on the same page. The box is `pointer-events-none`: the spotlighted element
   is VISUAL ONLY during the tour, so a click "through" the hole still lands on
   the full-screen container underneath and closes the tour like any other
   backdrop click — real navigation only happens through the bubble's buttons
   or its CTA link, never by tricking the user into clicking the live page.

   Bubble placement is plain viewport-coordinate arithmetic off
   `getBoundingClientRect()` — physical pixels, so it is RTL-safe by
   construction without any logical-direction math. `dir` is applied only to
   the bubble (its content reads in the active language); the full-screen
   overlay itself carries no `dir`, matching that its layout is physical, not
   logical.
   ═══════════════════════════════════════════════════════════════════════════ */

const CUTOUT_PADDING = 6
const BUBBLE_GAP = 12
const VIEWPORT_MARGIN = 12
const MOBILE_BREAKPOINT = 640
const FALLBACK_BUBBLE_W = 320
const FALLBACK_BUBBLE_H = 220

export type SpotlightStepContent = {
  icon: IconName
  chapter: string
  title: string
  body: string
  combo?: string
  ctaHref?: string
  ctaLabel?: string
}

type TourHeaderProps = {
  total: number
  idx: number
  onJump: (i: number) => void
  onClose: () => void
  stepOfLabel: string
  closeLabel: string
}

/** Progress dots (clickable to jump) + step counter + close. Shared by the
 *  centered card and the spotlight bubble — lifted, not reinvented. */
export function TourHeader({ total, idx, onJump, onClose, stepOfLabel, closeLabel }: TourHeaderProps) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-[var(--border)]">
      <div className="flex items-center gap-1.5" aria-hidden>
        {Array.from({ length: total }, (_, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onJump(i)}
            className="rounded-full transition-all"
            style={{
              width: i === idx ? '1.25rem' : '0.4rem',
              height: '0.4rem',
              background: i <= idx ? 'var(--accent)' : 'var(--border)',
            }}
          />
        ))}
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs text-[var(--text-muted)] num">{stepOfLabel}</span>
        <button type="button" onClick={onClose} className="btn btn-ghost btn-icon" aria-label={closeLabel}>
          <Icon name="close" size={16} />
        </button>
      </div>
    </div>
  )
}

type TourFooterProps = {
  isFirst: boolean
  isLast: boolean
  onPrev: () => void
  onNext: () => void
  onSkipOrClose: () => void
  skipLabel: string
  prevLabel: string
  nextLabel: string
  finishLabel: string
}

/** prev / next(finish); skip on the first step doubles as an escape hatch. */
export function TourFooter({
  isFirst,
  isLast,
  onPrev,
  onNext,
  onSkipOrClose,
  skipLabel,
  prevLabel,
  nextLabel,
  finishLabel,
}: TourFooterProps) {
  return (
    <div className="flex items-center justify-between gap-2 px-4 py-3 border-t border-[var(--border)]">
      <button type="button" onClick={isFirst ? onSkipOrClose : onPrev} className="btn btn-ghost btn-sm">
        {isFirst ? skipLabel : prevLabel}
      </button>
      <button type="button" onClick={onNext} className="btn btn-primary btn-sm">
        {isLast ? finishLabel : nextLabel}
      </button>
    </div>
  )
}

type TourBodyProps = {
  content: SpotlightStepContent
  lang: Lang
  onCtaClick: () => void
}

/** Chapter/icon row, title, optional combo badge, body copy, optional CTA. */
export function TourBody({ content, lang, onCtaClick }: TourBodyProps) {
  return (
    <div className="px-5 py-5 flex flex-col gap-3" dir={dirFor(lang)}>
      <div className="flex items-center gap-2 text-xs font-semibold text-[var(--accent)]">
        <Icon name={content.icon} size={16} />
        <span>{content.chapter}</span>
      </div>
      <h2 className="text-lg font-extrabold text-[var(--text-primary)]">{content.title}</h2>
      {content.combo && (
        <span className="self-start text-xs px-2 py-0.5 rounded-full border border-[var(--border)] text-[var(--text-secondary)] bg-[var(--bg-surface)]">
          {content.combo}
        </span>
      )}
      <p className="text-sm leading-8 text-[var(--text-secondary)]">{content.body}</p>
      {content.ctaHref && content.ctaLabel && (
        <Link href={content.ctaHref} onClick={onCtaClick} className="btn btn-secondary btn-sm self-start no-underline">
          {content.ctaLabel}
          <Icon name="arrowLeft" size={14} />
        </Link>
      )}
    </div>
  )
}

export type SpotlightOverlayProps = {
  /** Physical viewport rect of the live anchored element. */
  rect: DOMRect
  content: SpotlightStepContent
  lang: Lang
  dialogLabel: string
  header: Omit<TourHeaderProps, 'onClose'>
  footer: TourFooterProps
  onClose: () => void
  onCtaClick: () => void
}

export function SpotlightOverlay({ rect, content, lang, dialogLabel, header, footer, onClose, onCtaClick }: SpotlightOverlayProps) {
  const bubbleRef = useRef<HTMLDivElement>(null)
  const [bubbleSize, setBubbleSize] = useState({ width: FALLBACK_BUBBLE_W, height: FALLBACK_BUBBLE_H })
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < MOBILE_BREAKPOINT)
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  // The bubble's real height/width depends on step copy length, so a fixed
  // estimate would misplace the above/below flip and the arrow. Re-measure
  // whenever the content (i.e. the step) changes.
  useLayoutEffect(() => {
    const el = bubbleRef.current
    if (!el || isMobile) return
    const measure = () => setBubbleSize({ width: el.offsetWidth, height: el.offsetHeight })
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [content, isMobile])

  // Land keyboard focus in the bubble on every step change.
  useEffect(() => {
    bubbleRef.current?.focus()
  }, [content])

  // Manual focus trap: two sentinels around the bubble content cycle Tab
  // back into the dialog instead of escaping to the (visually) covered page.
  const cycleTab = (e: React.KeyboardEvent, wrapToStart: boolean) => {
    if (e.key !== 'Tab') return
    e.preventDefault()
    const focusables = bubbleRef.current?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input, [tabindex]:not([tabindex="-1"])',
    )
    if (!focusables || focusables.length === 0) return
    const target = wrapToStart ? focusables[0] : focusables[focusables.length - 1]
    target.focus()
  }

  let bubbleStyle: React.CSSProperties
  let arrowLeft: number | null = null
  let placeAbove = false

  if (isMobile) {
    bubbleStyle = { position: 'fixed', left: 0, right: 0, bottom: 0, width: '100%' }
  } else {
    const targetCenterX = rect.left + rect.width / 2
    const spaceBelow = window.innerHeight - rect.bottom
    placeAbove = spaceBelow < bubbleSize.height + 16
    let top = placeAbove ? rect.top - BUBBLE_GAP - bubbleSize.height : rect.bottom + BUBBLE_GAP
    top = Math.min(Math.max(top, VIEWPORT_MARGIN), window.innerHeight - bubbleSize.height - VIEWPORT_MARGIN)
    let left = targetCenterX - bubbleSize.width / 2
    left = Math.min(Math.max(left, VIEWPORT_MARGIN), window.innerWidth - bubbleSize.width - VIEWPORT_MARGIN)
    arrowLeft = Math.min(Math.max(targetCenterX - left, 16), bubbleSize.width - 16)
    bubbleStyle = { position: 'fixed', top, left, width: `min(360px, calc(100vw - ${VIEWPORT_MARGIN * 2}px))` }
  }

  return (
    <div className="fixed inset-0 z-[100] overflow-hidden" onClick={onClose}>
      {/* Cutout — see file header for the box-shadow trick. */}
      <div
        className="fixed pointer-events-none transition-all duration-[250ms] ease-in-out"
        style={{
          top: rect.top - CUTOUT_PADDING,
          left: rect.left - CUTOUT_PADDING,
          width: rect.width + CUTOUT_PADDING * 2,
          height: rect.height + CUTOUT_PADDING * 2,
          borderRadius: 'var(--radius-lg)',
          boxShadow: '0 0 0 200vmax rgba(0,0,0,0.6)',
        }}
      />

      {!isMobile && arrowLeft != null && (
        <div
          aria-hidden
          className="fixed w-3 h-3 bg-[var(--bg-elevated)] pointer-events-none"
          style={{
            left: (bubbleStyle.left as number) + arrowLeft - 6,
            top: placeAbove ? (bubbleStyle.top as number) + bubbleSize.height - 6 : (bubbleStyle.top as number) - 6,
            transform: 'rotate(45deg)',
            borderColor: 'var(--border)',
            borderStyle: 'solid',
            borderWidth: placeAbove ? '0 1px 1px 0' : '1px 0 0 1px',
          }}
        />
      )}

      <div
        ref={bubbleRef}
        role="dialog"
        aria-modal="true"
        aria-label={dialogLabel}
        dir={dirFor(lang)}
        tabIndex={-1}
        style={bubbleStyle}
        className={
          isMobile
            ? 'bg-[var(--bg-elevated)] border-t border-[var(--border)] rounded-t-[var(--radius-xl)] shadow-[var(--shadow-lg)] overflow-hidden fade-in outline-none'
            : 'bg-[var(--bg-elevated)] border border-[var(--border)] rounded-[var(--radius-xl)] shadow-[var(--shadow-lg)] overflow-hidden fade-in outline-none'
        }
        onClick={(e) => e.stopPropagation()}
      >
        <div tabIndex={0} onKeyDown={(e) => cycleTab(e, true)} />
        <TourHeader {...header} onClose={onClose} />
        <TourBody content={content} lang={lang} onCtaClick={onCtaClick} />
        <TourFooter {...footer} />
        <div tabIndex={0} onKeyDown={(e) => cycleTab(e, false)} />
      </div>
    </div>
  )
}
