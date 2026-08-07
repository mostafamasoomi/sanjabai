'use client'

import dynamic from 'next/dynamic'

// three.js is ~600KB of client JS the rest of this mostly-static page has no
// other use for, so it's code-split into its own chunk and only ever loaded
// in the browser — the effect is decorative, nothing about it needs to exist
// in the server-rendered HTML.
const Vortex = dynamic(() => import('./Vortex'), { ssr: false })

/**
 * Full-bleed animated banner sitting above everything else on the page,
 * including the fixed header (which floats over it, transparent, the same
 * way it floats over the hero below). Purely visual — no copy of its own —
 * so it stays a fixed dark backdrop in both themes rather than trying to
 * react to the light/dark toggle.
 */
export function VortexIntro() {
  return (
    <div className="lp-vortex-intro" aria-hidden="true">
      <Vortex style={{ width: '100%', height: '100%' }} />
    </div>
  )
}
