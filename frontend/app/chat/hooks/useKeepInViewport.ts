'use client'

import { useLayoutEffect, type RefObject } from 'react'

/* ═══════════════════════════════════════════════════════════════════════════
   Keeps a `position: absolute` popover inside the horizontal viewport.

   Extracted from SmartModePopover.tsx's original fix (session 2026-08-28):
   several dropdowns here (`.export-dropdown`, `.model-picker-dropdown`) are
   anchored with a logical inset (`inset-inline-start`/`-end`: 0) against
   THEIR OWN containing block -- the trigger's own box -- not the viewport.
   When that trigger sits away from the screen edge (which `justify-content:
   space-between` on `.chat-model-bar` routinely produces), the popover's far
   edge lands off-screen. Measured on both directions:
     - SmartModePopover (`inset-inline-end`, RTL): overflowed the RIGHT edge,
       up to +100px on a 375px screen.
     - ModelPicker (`inset-inline-start`, RTL): overflows the LEFT edge, up
       to -130px on a 768px screen (and the opposite edge is fine at 1280px,
       where the trigger already sits far enough right).

   The fix does not touch the CSS anchor at all -- that would require picking
   one direction and would still break at some width. Instead it measures the
   REAL rendered box after layout and nudges it back in with a plain
   `translateX`, which is direction-agnostic: it doesn't care whether the
   overflow is on the RTL-left or the RTL/LTR-right, and it works for BOTH
   `inset-inline-start` and `inset-inline-end` anchoring without change.
   ═══════════════════════════════════════════════════════════════════════════ */

/**
 * @param ref  The popover element itself (must be `position: absolute` or
 *             `fixed` already -- this hook only adds a corrective transform).
 * @param open Recomputes from a fresh measurement every time this flips to
 *             true, and on window resize while it stays true, so the
 *             correction never accumulates drift from a stale measurement.
 * @param pad  Minimum gap kept from either viewport edge, in px.
 */
export function useKeepInViewport(
  ref: RefObject<HTMLElement | null>,
  open: boolean,
  pad = 8,
): void {
  useLayoutEffect(() => {
    if (!open) return
    const reposition = () => {
      const el = ref.current
      if (!el) return
      // Reset first: the previous measurement's correction must not feed
      // into this one, or a resize could ratchet the offset in one direction.
      el.style.transform = ''
      const rect = el.getBoundingClientRect()
      let dx = 0
      if (rect.right > window.innerWidth - pad) dx = (window.innerWidth - pad) - rect.right
      if (rect.left + dx < pad) dx = pad - rect.left
      el.style.transform = dx ? `translateX(${dx}px)` : ''
    }
    reposition()
    window.addEventListener('resize', reposition)
    return () => window.removeEventListener('resize', reposition)
  }, [ref, open, pad])
}
