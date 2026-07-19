'use client'

import { useEffect, useRef } from 'react'

/* Routing-graph ambient field — motion.page energy.
   Reacts to scroll: as you scroll the hero in, the field focuses (nodes pull
   toward center, a faint "vortex" emerges) then releases. Driven by a
   --scroll-0..1 CSS var on <html> set by the page scroll hook. */

interface Node {
  x: number
  y: number
  vx: number
  vy: number
  r: number
  hue: number
  edge: boolean // true = outer ambient node, drifts
}

export default function VortexParticles() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let nodes: Node[] = []
    let width = 0
    let height = 0
    let raf = 0
    let reduced = false
    let scroll = 0

    const colors = [
      { r: 79, g: 178, b: 246 }, // blue
      { r: 175, g: 71, b: 255 }, // violet
      { r: 48, g: 218, b: 220 }, // teal
    ]

    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onMq = () => { reduced = mq.matches }
    onMq()
    mq.addEventListener?.('change', onMq)

    const onScrollVar = () => {
      const v = getComputedStyle(document.documentElement).getPropertyValue('--scroll')
      scroll = parseFloat(v) || 0
    }
    onScrollVar()
    window.addEventListener('scroll', onScrollVar, { passive: true })

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      width = canvas!.clientWidth || window.innerWidth
      height = canvas!.clientHeight || window.innerHeight
      canvas!.width = Math.floor(width * dpr)
      canvas!.height = Math.floor(height * dpr)
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    function seed() {
      const count = Math.min(Math.floor((width * height) / 16000), 80)
      nodes = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.22,
        vy: (Math.random() - 0.5) * 0.22,
        r: Math.random() * 1.6 + 0.7,
        hue: Math.floor(Math.random() * colors.length),
        edge: Math.random() > 0.35,
      }))
    }

    let t = 0
    function frame() {
      t += 0.006
      const focus = Math.min(1, scroll * 1.4) // 0 at top → 1 after a bit of scroll
      const cx = width * 0.5
      const cy = height * 0.5
      ctx!.clearRect(0, 0, width, height)

      if (reduced) {
        for (const n of nodes) {
          const c = colors[n.hue]
          ctx!.beginPath()
          ctx!.arc(n.x, n.y, n.r, 0, Math.PI * 2)
          ctx!.fillStyle = `rgba(${c.r},${c.g},${c.b},0.16)`
          ctx!.fill()
        }
        raf = requestAnimationFrame(frame)
        return
      }

      // focus pull: nodes drift toward center as you scroll (vortex feel)
      for (const n of nodes) {
        n.x += n.vx
        n.y += n.vy
        if (n.edge) {
          // swirl around center
          const dx = n.x - cx
          const dy = n.y - cy
          const ang = Math.atan2(dy, dx) + 0.004
          const rad = Math.hypot(dx, dy) * (1 - focus * 0.0016)
          n.x = cx + Math.cos(ang) * rad
          n.y = cy + Math.sin(ang) * rad
          if (rad < 6) { n.x = Math.random() * width; n.y = Math.random() * height }
        } else if (focus > 0.02) {
          n.x += (cx + Math.cos(t + n.r) * 60 - n.x) * 0.02 * focus
          n.y += (cy + Math.sin(t + n.r) * 60 - n.y) * 0.02 * focus
        }
        if (n.x < -30) n.x = width + 30
        if (n.x > width + 30) n.x = -30
        if (n.y < -30) n.y = height + 30
        if (n.y > height + 30) n.y = -30
      }

      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i]
          const b = nodes[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const d = Math.hypot(dx, dy)
          if (d < 150) {
            const alpha = (1 - d / 150) * (0.07 + focus * 0.05)
            ctx!.beginPath()
            ctx!.moveTo(a.x, a.y)
            ctx!.lineTo(b.x, b.y)
            ctx!.strokeStyle = `rgba(79,178,246,${alpha})`
            ctx!.lineWidth = 0.7
            ctx!.stroke()
          }
        }
      }

      for (const n of nodes) {
        const c = colors[n.hue]
        const glow = n.edge ? 0.4 : 0.45 + focus * 0.35
        ctx!.beginPath()
        ctx!.arc(n.x, n.y, n.r, 0, Math.PI * 2)
        ctx!.fillStyle = `rgba(${c.r},${c.g},${c.b},${glow})`
        ctx!.fill()
      }

      raf = requestAnimationFrame(frame)
    }

    const onResize = () => { resize(); seed() }

    resize()
    seed()
    raf = requestAnimationFrame(frame)
    window.addEventListener('resize', onResize)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      window.removeEventListener('scroll', onScrollVar)
      mq.removeEventListener?.('change', onMq)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        opacity: 0.9,
        maskImage: 'radial-gradient(ellipse 75% 65% at 50% 42%, black 18%, transparent 78%)',
        WebkitMaskImage: 'radial-gradient(ellipse 75% 65% at 50% 42%, black 18%, transparent 78%)',
      }}
    />
  )
}
