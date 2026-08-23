/* The admin panel's bearer-token fetch wrapper.
 *
 * Lifted out of AdminPanel.tsx so every section can import it directly
 * instead of reaching into the shell component's module (AdminPanel.tsx
 * still re-exports `api` from here, because sections written before this
 * split import it from '../AdminPanel').
 *
 * The token lives in a module-level variable, never in localStorage: an
 * admin token that survives a tab close is a stolen admin token.
 */

import { errorDetail } from './apiError'

let TOKEN = ''
let onUnauthorized: (() => void) | null = null

export function setAdminToken(token: string): void {
  TOKEN = token
}

/** Registered once by the shell. Called the moment any admin request comes
 *  back 401, so an expired session returns the admin to the login screen
 *  instead of leaving every section stuck on a failed load. */
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn
}

export async function api(path: string, opts: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (TOKEN) headers['Authorization'] = 'Bearer ' + TOKEN
  const res = await fetch(path, { ...opts, headers })
  if (res.status === 401) {
    TOKEN = ''
    onUnauthorized?.()
    // Kept as the literal sentinel `unauthorized`: callers branch on this
    // exact string to tell "log back in" apart from a real error message
    // worth showing (see errMessage below and UserDetailDrawer's errMessage).
    throw new Error('unauthorized')
  }
  if (!res.ok) throw new Error(await errorDetail(res))
  return res
}

/** The message to show the admin for a failed call.
 *
 *  Every admin endpoint refuses with a Persian `detail` that says what was
 *  actually wrong; `api()` already surfaced it as the Error message, so the
 *  only thing left is to not throw it away. `unauthorized` is the one
 *  message never shown — the shell is already bouncing to the login screen
 *  and its own toast covers it. */
export function errMessage(err: unknown, generic: string): string {
  if (err instanceof Error && err.message && err.message !== 'unauthorized') return err.message
  return generic
}
