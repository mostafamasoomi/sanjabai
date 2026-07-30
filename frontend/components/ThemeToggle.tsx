'use client'

import { useState, useEffect } from 'react'

function SunGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="4.2" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M18.7 5.3l-1.4 1.4M6.7 17.3l-1.4 1.4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}

function MoonGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M20 14.2A8.2 8.2 0 0 1 9.8 4a8.2 8.2 0 1 0 10.2 10.2Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function ThemeToggle() {
  const [dark, setDark] = useState(true)

  // The theme itself is applied before first paint by the bootstrap script in
  // app/layout.tsx. This only mirrors whatever that script decided, so the
  // icon matches the page instead of flashing the wrong one on hydration.
  useEffect(() => {
    setDark(document.documentElement.getAttribute('data-theme') !== 'light')
  }, [])

  const toggle = () => {
    const next = !dark
    setDark(next)
    try {
      localStorage.setItem('theme', next ? 'dark' : 'light')
    } catch {}
    document.documentElement.setAttribute('data-theme', next ? 'dark' : 'light')
  }

  const label = dark ? 'تغییر به حالت روشن' : 'تغییر به حالت تاریک'

  return (
    <button onClick={toggle} className="btn btn-ghost btn-icon" aria-label={label} title={label}>
      {dark ? <SunGlyph /> : <MoonGlyph />}
    </button>
  )
}
