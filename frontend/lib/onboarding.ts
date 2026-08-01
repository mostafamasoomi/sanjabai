'use client'

/* ═══════════════════════════════════════════════════════════════════════════
   Onboarding first-visit detection

   Lightweight, client-only. We persist a single localStorage flag once the
   user has completed onboarding. Combined with a "no conversations yet" API
   check (see AppShell guard), this routes first-time users to /onboarding
   and prevents re-showing it on later visits.
   ═══════════════════════════════════════════════════════════════════════════ */

const ONBOARDED_KEY = 'sanjhubai_onboarded'

export function markOnboarded() {
  try {
    localStorage.setItem(ONBOARDED_KEY, '1')
  } catch {
    /* ignore quota / private mode */
  }
}

export function isOnboarded(): boolean {
  try {
    return localStorage.getItem(ONBOARDED_KEY) === '1'
  } catch {
    return false
  }
}

/** Derive a friendly display name from the auth user. */
export function displayName(email?: string | null): string {
  if (!email) return ''
  const local = email.split('@')[0] || ''
  const cleaned = local.replace(/[._\-+]+/g, ' ').trim()
  if (!cleaned) return email
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1)
}
