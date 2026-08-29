'use client'

import { useState, useEffect, useCallback } from 'react'
import type { ReactNode } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useLang } from './LanguageToggle'
import { productTourStrings, TOUR_STEP_ORDER, type TourStep } from './ProductTour.strings'
import { useAnchorRect } from './tour/useAnchorRect'
import { SpotlightOverlay, TourHeader, TourFooter, TourBody } from './tour/SpotlightOverlay'

/* ═══════════════════════════════════════════════════════════════════════════
   Product tour — launch-anytime, anchored-spotlight coach-mark tour.

   Mirrors useCommandPalette's shape exactly (returns the rendered element +
   an imperative opener; AppShellInner renders {ProductTour}) so wiring is one
   line in the shell. Opened three ways, all funnelling through the same
   `open` state:
     1. the top-bar help button calls openTour() directly;
     2. any page (e.g. /guide) dispatches window CustomEvent TOUR_OPEN_EVENT —
        the same global-listener trick CommandPalette uses for ⌘K, so no
        shared React context is needed;
     3. Escape closes.

   v2 (this file): steps with a `route`/`anchor` land ON the real element on
   the real page instead of a generic centered popup — see
   components/tour/anchors.ts, useAnchorRect.ts and SpotlightOverlay.tsx. A
   step with neither renders the plain centered card (`CenteredStep` below),
   same shape as v1. Every anchored step still carries ctaHref/ctaLabel
   because the anchored path can ALWAYS fall back to that centered card —
   logged out, route bounced to /login, element never mounted, whatever the
   reason: the tour must never dead-end.

   Engine state machine, per active step:
     no anchor/route          → 'centered'  (CenteredStep, as v1)
     anchor+route, wrong path → router.push(route), 'waiting'
     anchor+route, right path → useAnchorRect polls; found → 'anchored'
                                 (SpotlightOverlay), timeout/unmount/`/login`
                                 → 'fallback' (CenteredStep, same renderer)
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

type CenteredStepProps = {
  step: TourStep
  lang: ReturnType<typeof useLang>
  dialogLabel: string
  idx: number
  total: number
  isFirst: boolean
  isLast: boolean
  onJump: (i: number) => void
  onClose: () => void
  onPrev: () => void
  onNext: () => void
  stepOfLabel: string
  closeLabel: string
  skipLabel: string
  prevLabel: string
  nextLabel: string
  finishLabel: string
}

/** The v1 renderer, kept verbatim as the welcome step AND the anchored-tour
 *  fallback (element never appeared). Header/footer are the same components
 *  SpotlightOverlay uses — lifted, not duplicated. */
function CenteredStep({
  step,
  lang,
  dialogLabel,
  idx,
  total,
  isFirst,
  isLast,
  onJump,
  onClose,
  onPrev,
  onNext,
  stepOfLabel,
  closeLabel,
  skipLabel,
  prevLabel,
  nextLabel,
  finishLabel,
}: CenteredStepProps) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={dialogLabel}
        className="relative w-full max-w-md bg-[var(--bg-elevated)] border border-[var(--border)] rounded-[var(--radius-xl)] shadow-[var(--shadow-lg)] overflow-hidden fade-in"
        onClick={(e) => e.stopPropagation()}
      >
        <TourHeader total={total} idx={idx} onJump={onJump} onClose={onClose} stepOfLabel={stepOfLabel} closeLabel={closeLabel} />
        <TourBody content={step} lang={lang} onCtaClick={onClose} />
        <TourFooter
          isFirst={isFirst}
          isLast={isLast}
          onPrev={onPrev}
          onNext={onNext}
          onSkipOrClose={onClose}
          skipLabel={skipLabel}
          prevLabel={prevLabel}
          nextLabel={nextLabel}
          finishLabel={finishLabel}
        />
      </div>
    </div>
  )
}

export function useProductTour() {
  const lang = useLang()
  const s = productTourStrings(lang)
  const [open, setOpen] = useState(false)
  const [idx, setIdx] = useState(0)
  const pathname = usePathname()
  const router = useRouter()

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
  const close = () => setOpen(false)
  const onJump = (i: number) => setIdx(i)

  const isAnchoredStep = !!step.anchor && !!step.route
  const onTargetRoute = isAnchoredStep && pathname === step.route

  // Navigate to the step's route the instant an anchored step activates.
  // Re-runs only when the step or path actually changes, so it never fights
  // a user who navigates away mid-tour.
  useEffect(() => {
    if (!open || !isAnchoredStep || onTargetRoute) return
    router.push(step.route!)
  }, [open, isAnchoredStep, onTargetRoute, step.route, router])

  const anchorActive = open && isAnchoredStep && onTargetRoute
  const { rect, status } = useAnchorRect(step.anchor, anchorActive)

  // An auth redirect while navigating is a dead end for the anchor by
  // definition — the target lives on a page the user was bounced off of.
  const loginBounce = open && isAnchoredStep && pathname === '/login'

  type EngineState = 'idle' | 'centered' | 'waiting' | 'anchored' | 'fallback'
  let engineState: EngineState
  if (!open) engineState = 'idle'
  else if (!isAnchoredStep) engineState = 'centered'
  else if (loginBounce || status === 'timeout') engineState = 'fallback'
  else if (onTargetRoute && status === 'found' && rect) engineState = 'anchored'
  else engineState = 'waiting'

  const stepOfLabel = s.stepOf(String(idx + 1), String(total))
  const headerCommon = { total, idx, onJump, stepOfLabel, closeLabel: s.close }
  const footerCommon = {
    isFirst,
    isLast,
    onPrev: prev,
    onNext: next,
    onSkipOrClose: close,
    skipLabel: s.skip,
    prevLabel: s.prev,
    nextLabel: s.next,
    finishLabel: s.finish,
  }

  let ProductTour: ReactNode = null
  if (engineState === 'centered' || engineState === 'fallback') {
    ProductTour = (
      <CenteredStep
        step={step}
        lang={lang}
        dialogLabel={s.dialogLabel}
        idx={idx}
        total={total}
        isFirst={isFirst}
        isLast={isLast}
        onJump={onJump}
        onClose={close}
        onPrev={prev}
        onNext={next}
        stepOfLabel={stepOfLabel}
        closeLabel={s.close}
        skipLabel={s.skip}
        prevLabel={s.prev}
        nextLabel={s.next}
        finishLabel={s.finish}
      />
    )
  } else if (engineState === 'anchored' && rect) {
    ProductTour = (
      <SpotlightOverlay
        rect={rect}
        content={step}
        lang={lang}
        dialogLabel={s.dialogLabel}
        header={headerCommon}
        footer={footerCommon}
        onClose={close}
        onCtaClick={close}
      />
    )
  }
  // engineState === 'waiting' renders nothing: the route just changed and the
  // element hasn't mounted yet (or the previous anchor is being re-measured
  // for the next step). Transient — resolves to 'anchored' or 'fallback'
  // within ANCHOR_TIMEOUT_MS, never left hanging.

  return { open, setOpen, openTour, ProductTour, launchLabel: s.launchTitle }
}
