'use client'

import { useEffect, useRef } from 'react'

/* ═══════════════════════════════════════════════════════════════════════════
   VortexParticles — Canvas-based particle field inspired by motion.page
   Subtle floating particles with gentle movement and fade edges.
   ═══════════════════════════════════════════════════════════════════════════ */

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  size: number
  opacity: number
  pulse: number
}

export default function VortexParticles() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let particles: Particle[] = []
    let animationId: number
    let width = 0
    let height = 0

    const ACCENT = { r: 129, g: 140, b: 248 } // indigo
    const WHITE = { r: 223, g: 225, b: 244 } // motion.page text color

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      width = window.innerWidth
      height = window.innerHeight
      canvas!.width = width * dpr
      canvas!.height = height * dpr
      canvas!.style.width = `${width}px`
      canvas!.style.height = `${height}px`
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    function createParticles() {
      const count = Math.min(Math.floor((width * height) / 12000), 120)
      particles = []
      for (let i = 0; i < count; i++) {
        particles.push({
          x: Math.random() * width,
          y: Math.random() * height,
          vx: (Math.random() - 0.5) * 0.2,
          vy: (Math.random() - 0.5) * 0.2 - 0.1,
          size: Math.random() * 1.5 + 0.5,
          opacity: Math.random() * 0.4 + 0.1,
          pulse: Math.random() * Math.PI * 2,
        })
      }
    }

    function draw(timestamp: number) {
      ctx!.clearRect(0, 0, width, height)

      const t = timestamp * 0.001

      for (const p of particles) {
        p.x += p.vx
        p.y += p.vy

        // Wrap around
        if (p.x < -50) p.x = width + 50
        if (p.x > width + 50) p.x = -50
        if (p.y < -50) p.y = height + 50
        if (p.y > height + 50) p.y = -50

        // Pulsing opacity
        const pulse = Math.sin(t * 0.8 + p.pulse) * 0.15 + 0.85
        const alpha = p.opacity * pulse

        // Distance from center — closer to center = more accent-colored
        const cx = width / 2
        const cy = height / 2
        const dx = (p.x - cx) / (width / 2)
        const dy = (p.y - cy) / (height / 2)
        const dist = Math.sqrt(dx * dx + dy * dy)

        // Blend between accent (center) and white (edges)
        const blend = Math.max(0, 1 - dist * 1.5)
        const r = Math.round(ACCENT.r * blend + WHITE.r * (1 - blend))
        const g = Math.round(ACCENT.g * blend + WHITE.g * (1 - blend))
        const b = Math.round(ACCENT.b * blend + WHITE.b * (1 - blend))

        ctx!.beginPath()
        ctx!.arc(p.x, p.y, p.size, 0, Math.PI * 2)
        ctx!.fillStyle = `rgba(${r},${g},${b},${alpha})`
        ctx!.fill()
      }

      // Draw subtle connections between nearby particles
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x
          const dy = particles[i].y - particles[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < 120) {
            const alpha = (1 - dist / 120) * 0.06
            ctx!.beginPath()
            ctx!.moveTo(particles[i].x, particles[i].y)
            ctx!.lineTo(particles[j].x, particles[j].y)
            ctx!.strokeStyle = `rgba(129,140,248,${alpha})`
            ctx!.lineWidth = 0.5
            ctx!.stroke()
          }
        }
      }

      animationId = requestAnimationFrame(draw)
    }

    resize()
    createParticles()
    animationId = requestAnimationFrame(draw)

    window.addEventListener('resize', () => {
      resize()
      createParticles()
    })

    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener('resize', resize)
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
        maskImage: 'radial-gradient(ellipse 80% 60% at 50% 0%, black 40%, transparent 75%)',
        WebkitMaskImage: 'radial-gradient(ellipse 80% 60% at 50% 0%, black 40%, transparent 75%)',
      }}
    />
  )
}