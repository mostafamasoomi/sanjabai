"use client"

import dynamic from 'next/dynamic'

const Vortex = dynamic(() => import('./Vortex'), { ssr: false })

export function VortexIntro() {
  return (
    <div className="lp-vortex-intro" aria-hidden="true">
      <Vortex
        style={{ width: '100%', height: '100%' }}
        background="transparent"
        cometOptions={{ color: '#e46b25', glow: 12, count: 25, speed: 12, delay: 0 }}
        lineOptions={{ color: '#b37926', glow: 6, count: 180 }}
        dotOptions={{ color: '#645630', glow: 4, count: 6000, size: 15, flicker: 8 }}
      />
    </div>
  )
}
