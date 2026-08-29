'use client'

import { useEffect, useRef, useState } from 'react'
import { findAnchor, type TourAnchorId } from './anchors'

/* ═══════════════════════════════════════════════════════════════════════════
   useAnchorRect — waits for a tour-anchored element to mount, scrolls it
   into view, and keeps its bounding rect fresh while the tour step is active.

   Three phases, tracked as `status`:
     'waiting' → polling for the element (rAF loop + a MutationObserver on
                 document.body, since the target can appear well after this
                 hook starts — a route just navigated, data is still loading).
     'found'   → element located, scrolled into view, rect measured; re-measured
                 on resize/scroll so the spotlight tracks a still-settling layout.
     'timeout' → ANCHOR_TIMEOUT_MS elapsed with no element. The caller (the
                 tour engine) falls back to the centered card — never a silent
                 dead end.

   All listeners/observers/rAF handles are torn down on unmount AND the instant
   `active` flips false, so switching steps never leaks a stale observer onto
   the next one.
   ═══════════════════════════════════════════════════════════════════════════ */

export const ANCHOR_TIMEOUT_MS = 4000

export type AnchorRectStatus = 'waiting' | 'found' | 'timeout'

export function useAnchorRect(anchorId: TourAnchorId | undefined, active: boolean) {
  const [rect, setRect] = useState<DOMRect | null>(null)
  const [status, setStatus] = useState<AnchorRectStatus>('waiting')

  // Mutable across renders without re-subscribing effects.
  const elRef = useRef<HTMLElement | null>(null)
  const rafRef = useRef<number | null>(null)
  const measureRafRef = useRef<number | null>(null)

  useEffect(() => {
    if (!active || !anchorId) {
      setRect(null)
      setStatus('waiting')
      return
    }

    let cancelled = false
    elRef.current = null
    setRect(null)
    setStatus('waiting')

    const deadline = Date.now() + ANCHOR_TIMEOUT_MS

    const measure = () => {
      const el = elRef.current
      if (!el || cancelled) return
      setRect(el.getBoundingClientRect())
    }

    const scheduleMeasure = () => {
      if (measureRafRef.current != null) return
      measureRafRef.current = requestAnimationFrame(() => {
        measureRafRef.current = null
        measure()
      })
    }

    const onFound = (el: HTMLElement) => {
      elRef.current = el
      // block: 'center' — the target lands mid-viewport so the spotlight
      // never sits half off-screen on a short mobile viewport.
      el.scrollIntoView({ block: 'center', behavior: 'smooth' })
      setStatus('found')
      measure()
    }

    // Poll via rAF: cheaper than setInterval to pause with the tab, and
    // catches elements that appear between MutationObserver batches.
    const poll = () => {
      if (cancelled) return
      const existing = elRef.current
      if (existing && document.contains(existing)) {
        // Already found; nothing to poll for. (rAF loop stops once found —
        // the MutationObserver below also watches for the element vanishing.)
        return
      }
      const el = findAnchor(anchorId)
      if (el) {
        onFound(el)
        return
      }
      if (Date.now() >= deadline) {
        setStatus('timeout')
        return
      }
      rafRef.current = requestAnimationFrame(poll)
    }
    rafRef.current = requestAnimationFrame(poll)

    // Element can also appear from a data fetch resolving well after mount —
    // the MutationObserver catches that without waiting for the next rAF poll.
    // It also catches the found element being torn back OUT of the DOM (e.g.
    // the list it lives in re-renders empty) and reports that as a timeout so
    // the engine falls back instead of spotlighting a detached rect.
    const mo = new MutationObserver(() => {
      if (cancelled) return
      if (elRef.current) {
        if (!document.contains(elRef.current)) {
          elRef.current = null
          setStatus('timeout')
        }
        return
      }
      const el = findAnchor(anchorId)
      if (el) onFound(el)
    })
    mo.observe(document.body, { childList: true, subtree: true })

    const onResize = () => scheduleMeasure()
    // Capture phase: catches scroll on any inner scroll container, not just
    // window — the anchor can be inside a scrollable list.
    const onScroll = () => scheduleMeasure()
    window.addEventListener('resize', onResize)
    window.addEventListener('scroll', onScroll, true)

    return () => {
      cancelled = true
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
      if (measureRafRef.current != null) cancelAnimationFrame(measureRafRef.current)
      mo.disconnect()
      window.removeEventListener('resize', onResize)
      window.removeEventListener('scroll', onScroll, true)
      elRef.current = null
    }
  }, [anchorId, active])

  return { rect, status }
}
