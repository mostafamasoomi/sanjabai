'use client'

import { useSyncExternalStore } from 'react'

/* ═══════════════════════════════════════════════════════════════════════════
   Language: one store, no reload.

   `toggle()` used to end in `window.location.reload()` — the cheap way to get
   every component that had read the language once at mount to read it again.
   In the admin panel that was a logout. The admin bearer token deliberately
   lives in a module variable and never in localStorage ("an admin token that
   survives a tab close is a stolen admin token", admin/api.ts), so reloading
   the page throws it away: flipping to English bounced the admin back to the
   login screen and cost them whatever they were in the middle of.

   The fix is to stop needing the reload. `setLang` publishes the change and
   `useLang` subscribes to it, so a flip re-renders the components that care
   and touches nothing else — no navigation, no remount, no lost token.

   `useSyncExternalStore` rather than useState+useEffect because the value
   lives outside React (localStorage, shared with the inline script in
   app/layout.tsx that applies dir before first paint). Its third argument is
   the server snapshot: 'fa' is the product default, and it must match what
   that script assumes or hydration would disagree with the markup.
   ═══════════════════════════════════════════════════════════════════════════ */

export type Lang = 'fa' | 'en'

const STORAGE_KEY = 'lang'
/** Namespaced so it cannot collide with an event from a third-party script. */
const LANG_EVENT = 'sanjab:langchange'

export function getLang(): Lang {
  if (typeof window === 'undefined') return 'fa'
  try {
    const v = (localStorage.getItem(STORAGE_KEY) || '') as Lang
    if (v === 'fa' || v === 'en') return v
  } catch {}
  return 'fa'
}

export function setLang(l: Lang) {
  try { localStorage.setItem(STORAGE_KEY, l) } catch {}
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('lang', l)
    document.documentElement.setAttribute('dir', l === 'fa' ? 'rtl' : 'ltr')
  }
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(LANG_EVENT, { detail: l }))
  }
}

function subscribe(onChange: () => void): () => void {
  if (typeof window === 'undefined') return () => {}
  window.addEventListener(LANG_EVENT, onChange)
  // Another tab flipping the language writes localStorage but cannot fire our
  // CustomEvent here; `storage` is how that crosses the tab boundary.
  window.addEventListener('storage', onChange)
  return () => {
    window.removeEventListener(LANG_EVENT, onChange)
    window.removeEventListener('storage', onChange)
  }
}

/** The current language, re-rendering the caller when it changes.
 *
 *  Safe to call from a server-rendered component: it reports 'fa' for the
 *  server pass and the real value once mounted. `getLang` returns a string,
 *  so the snapshot is referentially stable and this cannot loop. */
export function useLang(): Lang {
  return useSyncExternalStore(subscribe, getLang, () => 'fa')
}

export function LanguageToggle() {
  const lang = useLang()

  return (
    <button
      onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}
      className="btn btn-ghost btn-icon"
      aria-label={lang === 'fa' ? 'Switch to English' : 'تغییر به فارسی'}
      title={lang === 'fa' ? 'EN' : 'FA'}
    >
      {lang === 'fa' ? 'EN' : 'فا'}
    </button>
  )
}
