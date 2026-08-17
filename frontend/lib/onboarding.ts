'use client'

/* ═══════════════════════════════════════════════════════════════════════════
   Onboarding first-visit detection

   Lightweight, client-only. We persist a single localStorage flag once the
   user has completed onboarding. Combined with a "no conversations yet" API
   check (see AppShell guard), this routes first-time users to /onboarding
   and prevents re-showing it on later visits.
   ═══════════════════════════════════════════════════════════════════════════ */

const ONBOARDED_KEY = 'sanjabai_onboarded'
const LEGACY_ONBOARDED_KEY = 'sanjhubai_onboarded' // TODO: Remove after 90 days

function migrateLegacyOnboarded(): void {
  try {
    if (localStorage.getItem(ONBOARDED_KEY)) return
    const legacy = localStorage.getItem(LEGACY_ONBOARDED_KEY)
    if (legacy) {
      localStorage.setItem(ONBOARDED_KEY, legacy)
      localStorage.removeItem(LEGACY_ONBOARDED_KEY)
    }
  } catch {
    /* ignore quota / private mode */
  }
}

export function markOnboarded() {
  try {
    localStorage.setItem(ONBOARDED_KEY, '1')
  } catch {
    /* ignore quota / private mode */
  }
}

export function isOnboarded(): boolean {
  migrateLegacyOnboarded()
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
