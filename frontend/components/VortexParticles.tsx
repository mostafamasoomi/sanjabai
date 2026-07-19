'use client'

import { useEffect, useRef } from 'react'

/* Routing-graph ambient field — motion.page energy without SaaS particle soup */

interface Node {
  x: number
  y: number
  vx: number
  vy: number
  r: number
  hue: number
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

    const colors = [
      { r: 79, g: 178, b: 246 },  // blue
      { r: 175, g: 71, b: 255 },  // violet
      { r: 48, g: 218, b: 220 },  // teal
    ]

    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onMq = () => { reduced = mq.matches }
    onMq()
    mq.addEventListener?.('change', onMq)

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      width = canvas!.clientWidth || window.innerWidth
      height = canvas!.clientHeight || window.innerHeight
      canvas!.width = Math.floor(width * dpr)
      canvas!.height = Math.floor(height * dpr)
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    function seed() {
      const count = Math.min(Math.floor((width * height) / 18000), 64)
      nodes = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.18,
        vy: (Math.random() - 0.5) * 0.18,
        r: Math.random() * 1.4 + 0.6,
        hue: Math.floor(Math.random() * colors.length),
      }))
    }

    function frame() {
      ctx!.clearRect(0, 0, width, height)
      if (reduced) {
        // static soft field
        for (const n of nodes) {
          const c = colors[n.hue]
          ctx!.beginPath()
          ctx!.arc(n.x, n.y, n.r, 0, Math.PI * 2)
          ctx!.fillStyle = `rgba(${c.r},${c.g},${c.b},0.18)`
          ctx!.fill()
        }
        return
      }

      for (const n of nodes) {
        n.x += n.vx
        n.y += n.vy
        if (n.x < -20) n.x = width + 20
        if (n.x > width + 20) n.x = -20
        if (n.y < -20) n.y = height + 20
        if (n.y > height + 20) n.y = -20
      }

      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i]
          const b = nodes[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const d = Math.hypot(dx, dy)
          if (d < 140) {
            const alpha = (1 - d / 140) * 0.08
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
        ctx!.beginPath()
        ctx!.arc(n.x, n.y, n.r, 0, Math.PI * 2)
        ctx!.fillStyle = `rgba(${c.r},${c.g},${c.b},0.45)`
        ctx!.fill()
      }

      raf = requestAnimationFrame(frame)
    }

    const onResize = () => {
      resize()
      seed()
    }

    resize()
    seed()
    raf = requestAnimationFrame(frame)
    window.addEventListener('resize', onResize)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
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
        opacity: 0.85,
        maskImage: 'radial-gradient(ellipse 70% 60% at 70% 45%, black 20%, transparent 75%)',
        WebkitMaskImage: 'radial-gradient(ellipse 70% 60% at 70% 45%, black 20%, transparent 75%)',
      }}
    />
  )
}
