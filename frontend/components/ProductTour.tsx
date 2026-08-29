'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { Icon } from './ui/Icon'
import { useLang } from './LanguageToggle'
import { dirFor } from '@/lib/i18n'
import { productTourStrings, TOUR_STEP_ORDER } from './ProductTour.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Product tour — launch-anytime, multi-step popup.

   Mirrors useCommandPalette's shape exactly (returns the rendered element +
   an imperative opener; AppShellInner renders {ProductTour}) so wiring is one
   line in the shell. Opened three ways, all funnelling through the same
   `open` state:
     1. the top-bar help button calls openTour() directly;
     2. any page (e.g. /guide) dispatches window CustomEvent TOUR_OPEN_EVENT —
        the same global-listener trick CommandPalette uses for ⌘K, so no
        shared React context is needed;
     3. Escape closes.

   Deliberately NOT a spotlight/coach-mark tour (owner chose the popup): it
   never targets real page DOM, so it can't break when a page's markup
   changes and needs no per-page instrumentation. Every step's CTA is a plain
   <Link> to a real route; productTour.test.ts asserts each href exists.
   ═══════════════════════════════════════════════════════════════════════════ */

export const TOUR_OPEN_EVENT = 'sanjabai:tour:open'
const SEEN_KEY = 'sanjabai_tour_seen'

/** True once the user has opened the tour at least once (per browser). Used
 *  by the launcher to show a one-time "new" nudge dot. Fails safe to "seen"
 *  so a storage error never nags. */
export function tourSeen(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === '1'
  } catch {
    return true
  }
}

export function useProductTour() {
  const lang = useLang()
  const s = productTourStrings(lang)
  const [open, setOpen] = useState(false)
  const [idx, setIdx] = useState(0)

  const openTour = useCallback(() => {
    setIdx(0)
    setOpen(true)
  }, [])

  // Global open event, so surfaces outside this component's subtree (the
  // /guide page, a future command-palette entry) can trigger the tour without
  // threading a callback through the tree.
  useEffect(() => {
    const onOpen = () => {
      setIdx(0)
      setOpen(true)
    }
    window.addEventListener(TOUR_OPEN_EVENT, onOpen)
    return () => window.removeEventListener(TOUR_OPEN_EVENT, onOpen)
  }, [])

  // Escape to close, and mark the tour seen the moment it opens. Arrow keys
  // are intentionally NOT bound: their meaning flips under RTL, so "next" is a
  // button, never a guessed key direction.
  useEffect(() => {
    if (!open) return
    try {
      localStorage.setItem(SEEN_KEY, '1')
    } catch {
      /* private mode / storage disabled — the tour still works, just no nudge memory */
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  const total = TOUR_STEP_ORDER.length
  const stepId = TOUR_STEP_ORDER[idx]
  const step = s.steps[stepId]
  const isFirst = idx === 0
  const isLast = idx === total - 1

  const next = () => (isLast ? setOpen(false) : setIdx((i) => Math.min(i + 1, total - 1)))
  const prev = () => setIdx((i) => Math.max(i - 1, 0))

  const ProductTour = open ? (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      onClick={() => setOpen(false)}
      dir={dirFor(lang)}
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={s.dialogLabel}
        className="relative w-full max-w-md bg-[var(--bg-elevated)] border border-[var(--border)] rounded-[var(--radius-xl)] shadow-[var(--shadow-lg)] overflow-hidden fade-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header: progress dots (clickable to jump) + step counter + close */}
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-[var(--border)]">
          <div className="flex items-center gap-1.5" aria-hidden>
            {TOUR_STEP_ORDER.map((id, i) => (
              <button
                key={id}
                type="button"
                onClick={() => setIdx(i)}
                className="rounded-full transition-all"
                style={{
                  width: i === idx ? '1.25rem' : '0.4rem',
                  height: '0.4rem',
                  background: i <= idx ? 'var(--accent)' : 'var(--border)',
                }}
                aria-label={s.stepOf(String(i + 1), String(total))}
              />
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--text-muted)] num">{s.stepOf(String(idx + 1), String(total))}</span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="btn btn-ghost btn-icon"
              aria-label={s.close}
            >
              <Icon name="close" size={16} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="px-5 py-5 flex flex-col gap-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-[var(--accent)]">
            <Icon name={step.icon} size={16} />
            <span>{step.chapter}</span>
          </div>
          <h2 className="text-lg font-extrabold text-[var(--text-primary)]">{step.title}</h2>
          {step.combo && (
            <span
              className="self-start text-xs px-2 py-0.5 rounded-full border border-[var(--border)] text-[var(--text-secondary)] bg-[var(--bg-surface)]"
              dir={dirFor(lang)}
            >
              {step.combo}
            </span>
          )}
          <p className="text-sm leading-8 text-[var(--text-secondary)]">{step.body}</p>
          {step.ctaHref && step.ctaLabel && (
            <Link
              href={step.ctaHref}
              onClick={() => setOpen(false)}
              className="btn btn-secondary btn-sm self-start no-underline"
            >
              {step.ctaLabel}
              <Icon name="arrowLeft" size={14} />
            </Link>
          )}
        </div>

        {/* Footer: prev / next(finish). Skip on the first step doubles as an
            escape hatch for a returning user who only wanted one section. */}
        <div className="flex items-center justify-between gap-2 px-4 py-3 border-t border-[var(--border)]">
          <button
            type="button"
            onClick={isFirst ? () => setOpen(false) : prev}
            className="btn btn-ghost btn-sm"
          >
            {isFirst ? s.skip : s.prev}
          </button>
          <button type="button" onClick={next} className="btn btn-primary btn-sm">
            {isLast ? s.finish : s.next}
          </button>
        </div>
      </div>
    </div>
  ) : null

  return { open, setOpen, openTour, ProductTour, launchLabel: s.launchTitle }
}
