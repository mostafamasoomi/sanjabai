'use client'

import { useEffect, useRef, useState } from 'react'
import { useTilt } from './useTilt'

interface RevealProps {
  children: React.ReactNode
  /** Stagger, in milliseconds, applied as a CSS transition-delay. */
  delay?: number
  className?: string
  as?: 'div' | 'section' | 'li' | 'article'
  /**
   * Adds pointer-driven 3D tilt + spotlight (see useTilt). Off by default —
   * only cards meant to read as physical objects (bento tiles, pricing
   * cards) should opt in; body copy and list rows stay flat.
   */
  tilt?: boolean
  /** Max rotation in degrees for the tilt effect. Ignored unless `tilt`. */
  tiltDeg?: number
}

/**
 * Fades content in the first time it enters the viewport.
 *
 * This replaces the page's GSAP + ScrollTrigger choreography, which ran a
 * scrubbed timeline on every scroll frame and animated `textContent` for the
 * stat counters (a layout-thrashing write per frame). One shared
 * IntersectionObserver per element, unobserved after it fires, and the whole
 * effect is opacity + translate — both compositor-only properties.
 */
export function Reveal({
  children,
  delay = 0,
  className = '',
  as = 'div',
  tilt = false,
  tiltDeg = 6,
}: RevealProps) {
  const ref = useRef<HTMLElement>(null)
  const [visible, setVisible] = useState(false)

  useTilt(ref, tilt, tiltDeg)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    // Without IntersectionObserver, or when the user asked for less motion,
    // show the content immediately rather than leaving it at opacity 0.
    if (
      typeof IntersectionObserver === 'undefined' ||
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ) {
      setVisible(true)
      return
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return
        setVisible(true)
        observer.disconnect()
      },
      { rootMargin: '0px 0px -12% 0px', threshold: 0.05 },
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const Tag = as as 'div'

  return (
    <Tag
      ref={ref as React.RefObject<HTMLDivElement>}
      className={`lp-reveal ${tilt ? 'lp-tilt' : ''} ${className}`.trim().replace(/\s+/g, ' ')}
      data-visible={visible}
      style={delay ? ({ '--lp-delay': `${delay}ms` } as React.CSSProperties) : undefined}
    >
      {children}
    </Tag>
  )
}
