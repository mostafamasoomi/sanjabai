'use client'

import { useEffect } from 'react'

/**
 * Lightweight smooth-scroll engine — the "motion.page" feel without a heavy dep.
 * Intercepts wheel/touch, lerps the scroll position toward a target each frame.
 * Falls back to native scroll for reduced-motion users and keyboard (anchors/space).
 */
export default function SmoothScroll() {
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (mq.matches) return

    // Skip on touch-only devices (native momentum is better there)
    const coarse = window.matchMedia('(pointer: coarse)').matches
    if (coarse) return

    let target = window.scrollY
    let current = window.scrollY
    let raf = 0
    let running = false
    const ease = 0.12

    const maxScroll = () =>
      Math.max(0, document.documentElement.scrollHeight - window.innerHeight)

    const loop = () => {
      current += (target - current) * ease
      if (Math.abs(target - current) < 0.4) {
        current = target
        window.scrollTo(0, current)
        running = false
        return
      }
      window.scrollTo(0, current)
      raf = requestAnimationFrame(loop)
    }

    const start = () => {
      if (!running) {
        running = true
        raf = requestAnimationFrame(loop)
      }
    }

    const onWheel = (e: WheelEvent) => {
      // let the browser handle zoom / horizontal
      if (e.ctrlKey) return
      e.preventDefault()
      const delta =
        e.deltaMode === 1 ? e.deltaY * 24 : e.deltaY // line vs pixel
      target = Math.min(maxScroll(), Math.max(0, target + delta))
      start()
    }

    let touchY = 0
    const onTouchStart = (e: TouchEvent) => {
      touchY = e.touches[0].clientY
      target = window.scrollY
      current = window.scrollY
    }
    const onTouchMove = (e: TouchEvent) => {
      const y = e.touches[0].clientY
      const delta = (touchY - y) * 1.6
      touchY = y
      target = Math.min(maxScroll(), Math.max(0, target + delta))
      start()
    }

    window.addEventListener('wheel', onWheel, { passive: false })
    window.addEventListener('touchstart', onTouchStart, { passive: true })
    window.addEventListener('touchmove', onTouchMove, { passive: true })

    return () => {
      window.removeEventListener('wheel', onWheel)
      window.removeEventListener('touchstart', onTouchStart)
      window.removeEventListener('touchmove', onTouchMove)
      cancelAnimationFrame(raf)
    }
  }, [])

  return null
}
