'use client'

import { useEffect } from 'react'

/**
 * Smooth scroll — exponential decay model.
 * Wheel input applies IMMEDIATELY to target, then current decays toward it.
 * No perceivable delay. The "smooth" comes from the tail deceleration only.
 */
export default function SmoothScroll() {
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (mq.matches) return
    const coarse = window.matchMedia('(pointer: coarse)').matches
    if (coarse) return

    let target = window.scrollY
    let current = window.scrollY
    let raf = 0

    const maxScroll = () =>
      Math.max(0, document.documentElement.scrollHeight - window.innerHeight)

    function tick() {
      const diff = target - current
      // Exponential decay: fast catch-up, smooth tail
      // 0.25 = responsive. < 0.15 = laggy. > 0.35 = too snappy (no smooth feel)
      current += diff * 0.25
      if (Math.abs(diff) < 0.5) {
        current = target
        window.scrollTo({ top: current, behavior: 'auto' })
        return
      }
      window.scrollTo({ top: current, behavior: 'auto' })
      raf = requestAnimationFrame(tick)
    }

    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey) return
      e.preventDefault()
      const delta = e.deltaMode === 1 ? e.deltaY * 24 : e.deltaY
      target = Math.min(maxScroll(), Math.max(0, target + delta))
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(tick)
    }

    window.addEventListener('wheel', onWheel, { passive: false })
    return () => {
      window.removeEventListener('wheel', onWheel)
      cancelAnimationFrame(raf)
    }
  }, [])

  return null
}
