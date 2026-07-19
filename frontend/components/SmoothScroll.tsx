'use client'

import { useEffect } from 'react'

/**
 * Lightweight smooth-scroll engine — motion.page DNA.
 * Intercepts wheel, lerps scroll position with HIGH ease for responsive feel.
 * Falls back to native scroll for reduced-motion / touch / keyboard.
 */
export default function SmoothScroll() {
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (mq.matches) return

    // Skip on touch-only devices (native momentum is better)
    const coarse = window.matchMedia('(pointer: coarse)').matches
    if (coarse) return

    let target = window.scrollY
    let current = window.scrollY
    let velocity = 0
    let raf = 0
    let running = false

    // High ease = responsive. Low friction = subtle momentum at end.
    const ease = 0.22
    const friction = 0.92

    const maxScroll = () =>
      Math.max(0, document.documentElement.scrollHeight - window.innerHeight)

    const loop = () => {
      const diff = target - current
      velocity = velocity * friction + diff * ease
      current += velocity

      if (Math.abs(diff) < 0.5 && Math.abs(velocity) < 0.5) {
        current = target
        window.scrollTo({ top: current, behavior: 'auto' })
        velocity = 0
        running = false
        return
      }
      window.scrollTo({ top: current, behavior: 'auto' })
      raf = requestAnimationFrame(loop)
    }

    const start = () => {
      if (!running) {
        running = true
        raf = requestAnimationFrame(loop)
      }
    }

    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey) return
      e.preventDefault()
      const delta =
        e.deltaMode === 1 ? e.deltaY * 24 : e.deltaY
      target = Math.min(maxScroll(), Math.max(0, target + delta * 1.1))
      start()
    }

    // Sync on programmatic scroll (anchor links, back/forward)
    const onPopState = () => {
      target = window.scrollY
      current = window.scrollY
      velocity = 0
    }
    window.addEventListener('popstate', onPopState)

    window.addEventListener('wheel', onWheel, { passive: false })

    return () => {
      window.removeEventListener('wheel', onWheel)
      window.removeEventListener('popstate', onPopState)
      cancelAnimationFrame(raf)
    }
  }, [])

  return null
}
