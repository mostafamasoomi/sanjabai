'use client'

import { useRef, useEffect } from 'react'

interface Particle {
  x: number
  y: number
  size: number
  speed: number
  angle: number
  life: number
}

export function VortexCanvas({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animationFrameId: number | null = null
    const particles: Particle[] = []
    const particleCount = 100 // Minimal set to fit budget

    // Resize
    const resize = () => {
      canvas.width = canvas.clientWidth * (window.devicePixelRatio || 1)
      canvas.height = canvas.clientHeight * (window.devicePixelRatio || 1)
    }
    window.addEventListener('resize', resize)
    resize()

    // Init
    for (let i = 0; i < particleCount; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        size: Math.random() * 2 + 1,
        speed: Math.random() * 2 + 0.5,
        angle: Math.random() * Math.PI * 2,
        life: Math.random(),
      })
    }

    // Render loop
    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      ctx.fillStyle = 'rgba(255, 255, 255, 0.5)'

      particles.forEach((p) => {
        p.x += Math.cos(p.angle) * p.speed
        p.y += Math.sin(p.angle) * p.speed
        p.angle += 0.05
        p.life -= 0.001

        if (p.life <= 0) {
          p.x = Math.random() * canvas.width
          p.y = Math.random() * canvas.height
          p.life = 1
        }

        ctx.beginPath()
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
        ctx.fill()
      })

      animationFrameId = requestAnimationFrame(render)
    }

    // Intersection Observer to stop when off-screen
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) {
        animationFrameId = requestAnimationFrame(render)
      } else if (animationFrameId !== null) {
        cancelAnimationFrame(animationFrameId)
      }
    })
    observer.observe(canvas)

    // Reduced motion check
    const mql = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (mql.matches && animationFrameId !== null) cancelAnimationFrame(animationFrameId)

    return () => {
      if (animationFrameId !== null) cancelAnimationFrame(animationFrameId)
      observer.disconnect()
      window.removeEventListener('resize', resize)
    }
  }, [])

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />
}