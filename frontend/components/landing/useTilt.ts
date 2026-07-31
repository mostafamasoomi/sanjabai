'use client'

import { useEffect, type RefObject } from 'react'

/**
 * Pointer-driven 3D tilt + spotlight, expressed purely as CSS custom
 * properties (`--tx`, `--ty`, `--mx`, `--my`) so the actual transform/gradient
 * lives in CSS and stays compositor-only (transform + a masked gradient,
 * nothing that reflows).
 *
 * Takes the target's own ref rather than returning one, so callers that
 * already track the node for something else (Reveal's IntersectionObserver)
 * can share a single ref instead of stitching two together.
 *
 * Deliberately inert on touch: `pointer: coarse` devices get the flat,
 * static card — tilt-on-touch has no natural "leave" gesture and just reads
 * as stuck. Also inert under `prefers-reduced-motion`.
 */
export function useTilt<T extends HTMLElement>(
  ref: RefObject<T | null>,
  enabled: boolean,
  maxDeg = 6,
) {
  useEffect(() => {
    const el = ref.current
    if (!el || !enabled) return
    if (
      !window.matchMedia('(pointer: fine)').matches ||
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ) {
      return
    }

    let frame = 0

    const onMove = (e: PointerEvent) => {
      if (frame) return
      frame = requestAnimationFrame(() => {
        frame = 0
        const rect = el.getBoundingClientRect()
        const px = (e.clientX - rect.left) / rect.width
        const py = (e.clientY - rect.top) / rect.height
        const rx = (0.5 - py) * maxDeg * 2
        const ry = (px - 0.5) * maxDeg * 2
        el.style.setProperty('--tx', `${rx.toFixed(2)}deg`)
        el.style.setProperty('--ty', `${ry.toFixed(2)}deg`)
        el.style.setProperty('--mx', `${(px * 100).toFixed(1)}%`)
        el.style.setProperty('--my', `${(py * 100).toFixed(1)}%`)
      })
    }

    const onLeave = () => {
      cancelAnimationFrame(frame)
      frame = 0
      el.style.setProperty('--tx', '0deg')
      el.style.setProperty('--ty', '0deg')
    }

    el.addEventListener('pointermove', onMove)
    el.addEventListener('pointerleave', onLeave)
    return () => {
      cancelAnimationFrame(frame)
      el.removeEventListener('pointermove', onMove)
      el.removeEventListener('pointerleave', onLeave)
    }
  }, [ref, enabled, maxDeg])
}
