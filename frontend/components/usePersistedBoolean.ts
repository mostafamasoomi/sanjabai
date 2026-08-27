'use client'

import { useCallback, useEffect, useState } from 'react'

/**
 * A boolean that starts at `defaultValue` and is reconciled with a
 * localStorage key right after mount, then kept in sync on every explicit
 * change made through the returned setter.
 *
 * Hydration-safe by construction: the initial render -- both the server pass
 * and the client's first render before hydration -- always uses
 * `defaultValue`, never localStorage. This mirrors `lib/auth.tsx`'s token
 * restore (state starts `null`, then a mount-only effect reads
 * `sanjabai_auth_token` and calls `setToken`), not `app/chat/page.tsx`'s
 * `smartMode`/`webSearch`, which read localStorage straight from the
 * `useState` initializer -- that reads a different value on the server (no
 * `window`) than on the client the instant a returning visitor has a stored
 * value, which is a hydration mismatch, not a cosmetic flash.
 *
 * The cost of the safe version is a one-frame delay before a returning
 * visitor's stored value applies (e.g. a collapsed sidebar briefly renders
 * expanded on first paint). That trade is intentional here.
 */
/** Same shape as `useState`'s setter -- a plain value or a `(prev) => next`
 *  updater -- so this drops into call sites written against `useState`
 *  (e.g. `app/chat/components/ChatModelBar.tsx`'s
 *  `setSidebarOpen: (updater: (prev: boolean) => boolean) => void` prop)
 *  without changing them. */
type BooleanSetter = boolean | ((prev: boolean) => boolean)

export function usePersistedBoolean(
  key: string,
  defaultValue: boolean,
): [boolean, (next: BooleanSetter) => void] {
  const [value, setValue] = useState(defaultValue)

  // The write happens in an effect keyed on the resolved value, NOT inside
  // the `setValue` updater. React may invoke an updater twice (StrictMode),
  // and an updater is required to be pure -- `localStorage.setItem` in there
  // is a side effect in a function that contractually may not have one. It is
  // idempotent, so it did no harm, but "harmless today" is how a rule gets
  // quietly broken for the next person who copies this hook.
  //
  // `hydrated` gates the very first write: without it, the mount effect above
  // and this one race, and a visitor whose stored value differs from the
  // default would have the default written back over their choice.
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    try {
      const stored = localStorage.getItem(key)
      if (stored === 'true' || stored === 'false') setValue(stored === 'true')
    } catch {
      /* localStorage unavailable (private mode, disabled storage) */
    }
    setHydrated(true)
  }, [key])

  useEffect(() => {
    if (!hydrated) return
    try {
      localStorage.setItem(key, value ? 'true' : 'false')
    } catch {
      /* best effort -- the toggle still works for the current session */
    }
  }, [key, value, hydrated])

  const setPersisted = useCallback((next: BooleanSetter) => {
    setValue((prev) => (typeof next === 'function' ? next(prev) : next))
  }, [])

  return [value, setPersisted]
}
