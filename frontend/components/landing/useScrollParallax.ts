'use client'

import { useEffect, type RefObject } from 'react'

/**
 * Cheap scroll-linked depth: each layer drifts a fraction of the page's
 * scroll distance, so a stack of blurred blobs reads as sitting at
 * different distances from the camera instead of scrolling as one flat
 * plane. Uses the standalone `translate` property (not `transform`) so it
 * composes without fighting the CSS keyframe drift animation already
 * running on `transform` for the same elements — both apply at once.
 *
 * The scroll listener is only attached while `boundary` is on screen (via
 * IntersectionObserver): there's no reason to keep computing an offset for
 * a background layer that scrolled out of view an hour ago.
 */
interface ParallaxLayer {
  ref: RefObject<HTMLElement | null>
  /** Fraction of scroll speed this layer drifts at. */
  depth: number
  /**
   * The layer's own resting x-translate (e.g. '-50%' for a blob centered via
   * `inset-inline-start: 50%` + `translate: -50% 0` in CSS). `el.style.translate`
   * is a full property overwrite, not a merge with the stylesheet value, so
   * without this every layer's horizontal position would collapse to 0 the
   * instant the scroll handler first ran.
   */
  baseX?: string
}

export function useScrollParallax(boundary: RefObject<HTMLElement | null>, layers: ParallaxLayer[]) {
  useEffect(() => {
    const root = boundary.current
    if (!root) return
    if (
      typeof IntersectionObserver === 'undefined' ||
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ) {
      return
    }

    let frame = 0
    let active = false

    const apply = () => {
      frame = 0
      const y = window.scrollY
      for (const { ref, depth, baseX = '0' } of layers) {
        const el = ref.current
        if (el) el.style.translate = `${baseX} ${(y * depth).toFixed(1)}px`
      }
    }

    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(apply)
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !active) {
          active = true
          apply()
          window.addEventListener('scroll', onScroll, { passive: true })
        } else if (!entry.isIntersecting && active) {
          active = false
          window.removeEventListener('scroll', onScroll)
          cancelAnimationFrame(frame)
          frame = 0
        }
      },
      { rootMargin: '40% 0px 40% 0px' },
    )
    observer.observe(root)

    return () => {
      observer.disconnect()
      window.removeEventListener('scroll', onScroll)
      cancelAnimationFrame(frame)
    }
  }, [boundary, layers])
}
