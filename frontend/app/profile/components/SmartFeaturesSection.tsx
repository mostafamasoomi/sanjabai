'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { smartFeaturesSectionStrings } from './SmartFeaturesSection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   P-UI-TOGGLES — two switches into the user's `preferences` object:
   `smart_router_enabled` (default true) and `compression_enabled` (default
   false). See SmartFeaturesSection.strings.ts for what the copy promises and
   does not promise.

   Self-contained by design, unlike its neighbours (AutonomySection,
   NotificationsSection, ...), which read/write state lifted into
   hooks/useProfileData.ts and only save on the page's single "Save Changes"
   button. This packet's scope is exactly {this file, its .strings.ts,
   page.tsx, the test} -- hooks/useProfileData.ts is not in scope and is not
   touched. So this component fetches its own copy of `GET /api/auth/profile`
   on mount and PUTs its own changes immediately per toggle (same pattern as
   app/wallet/components/EntitlementPanel.tsx: own useAuth(), own useEffect
   fetch, no props from the page).

   This does not conflict with the main Save button: the backend contract
   (`PUT /api/auth/profile` accepts `{preferences: {...}}`) merges preferences
   per key rather than replacing the whole object -- confirmed by the packet
   text "PUT .../profile accepts {preferences: {smart_router_enabled,
   compression_enabled}}" listing only these two keys as a valid body, which
   would silently wipe every other preference on every save if the merge were
   a full replace. The other sections' PUTs (which don't send these two keys)
   therefore leave them untouched, and this component's PUTs (which don't
   send default_model/theme/etc.) leave those untouched in turn.
   ═══════════════════════════════════════════════════════════════════════════ */

const DEFAULT_SMART_ROUTER_ENABLED = true
const DEFAULT_COMPRESSION_ENABLED = false

/** Pure preference-parsing, exported so tests/lib/smartFeatures.test.ts can
 *  exercise it directly without rendering a component (this repo has no
 *  React Testing Library -- see tests/lib/referralSignupChain.test.ts for
 *  the same note).
 *
 *  `??`, not `||`: an explicitly stored `false` (the user turned a switch
 *  off and it saved) must not be silently overridden back to the default by
 *  `false || default` -- that expression always evaluates to `default`
 *  because `false` is falsy, which is exactly the classic bug the packet
 *  asks this to guard against. */
export function parseSmartFeaturePrefs(preferences: Record<string, any> | null | undefined): {
  smartRouterEnabled: boolean
  compressionEnabled: boolean
} {
  const prefs = preferences || {}
  return {
    smartRouterEnabled: prefs.smart_router_enabled ?? DEFAULT_SMART_ROUTER_ENABLED,
    compressionEnabled: prefs.compression_enabled ?? DEFAULT_COMPRESSION_ENABLED,
  }
}

/** Pure payload-builder, exported for the same reason. Always sends both
 *  keys as real booleans via `Boolean(...)` (never `1`/`"true"`, which the
 *  backend's 400 on non-booleans would reject), and always sends the
 *  caller's last-known value for the switch that wasn't just touched, so a
 *  single toggle never has to guess what the other switch's value should be
 *  in the same request. */
export function buildSmartFeaturesPayload(smartRouterEnabled: boolean, compressionEnabled: boolean) {
  return {
    preferences: {
      smart_router_enabled: Boolean(smartRouterEnabled),
      compression_enabled: Boolean(compressionEnabled),
    },
  }
}

type SavingKey = 'smart_router_enabled' | 'compression_enabled' | null

export default function SmartFeaturesSection() {
  const { token } = useAuth()
  const lang = useLang()
  const s = smartFeaturesSectionStrings(lang)

  const [smartRouterEnabled, setSmartRouterEnabled] = useState(DEFAULT_SMART_ROUTER_ENABLED)
  const [compressionEnabled, setCompressionEnabled] = useState(DEFAULT_COMPRESSION_ENABLED)
  const [savingKey, setSavingKey] = useState<SavingKey>(null)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    ;(async () => {
      try {
        const r = await fetch('/api/auth/profile', {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (r.ok) {
          const data = await r.json()
          const parsed = parseSmartFeaturePrefs(data.preferences)
          if (!cancelled) {
            setSmartRouterEnabled(parsed.smartRouterEnabled)
            setCompressionEnabled(parsed.compressionEnabled)
          }
        }
      } catch {
        // Stays at the documented defaults; the switches remain usable, they
        // just start from the default rather than the account's saved choice.
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  const save = async (nextRouter: boolean, nextCompression: boolean, key: SavingKey, revert: () => void) => {
    setSavingKey(key)
    try {
      const r = await apiFetch('/api/auth/profile', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(buildSmartFeaturesPayload(nextRouter, nextCompression)),
      })
      if (!r.ok) {
        revert()
        const data = await r.json().catch(() => ({}))
        toast(data.detail || s.saveError, 'error')
      }
    } catch {
      revert()
      toast(s.saveError, 'error')
    } finally {
      setSavingKey(null)
    }
  }

  const handleToggleRouter = () => {
    const next = !smartRouterEnabled
    setSmartRouterEnabled(next)
    save(next, compressionEnabled, 'smart_router_enabled', () => setSmartRouterEnabled(!next))
  }

  const handleToggleCompression = () => {
    const next = !compressionEnabled
    setCompressionEnabled(next)
    save(smartRouterEnabled, next, 'compression_enabled', () => setCompressionEnabled(!next))
  }

  return (
    <div className="card profile-section-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="cpu" size={16} className="text-accent" />
        <h2 className="card-title">
          {s.title}
        </h2>
      </div>
      <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
        {s.intro}
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <div className="profile-toggle-row">
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
            <Icon name="cpu" size={16} className="text-muted" style={{ marginTop: 2 }} />
            <div>
              <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
                {s.smartRouterLabel}
              </span>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2, lineHeight: 1.6 }}>
                {s.smartRouterDesc}
              </p>
            </div>
          </div>
          <button
            className={`profile-toggle ${smartRouterEnabled ? 'active' : ''}`}
            onClick={handleToggleRouter}
            disabled={savingKey === 'smart_router_enabled'}
            role="switch"
            aria-checked={smartRouterEnabled}
          >
            <span className="profile-toggle-knob" />
          </button>
        </div>
        <div className="profile-toggle-row">
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
            <Icon name="history" size={16} className="text-muted" style={{ marginTop: 2 }} />
            <div>
              <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
                {s.compressionLabel}
              </span>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2, lineHeight: 1.6 }}>
                {s.compressionDesc}
              </p>
            </div>
          </div>
          <button
            className={`profile-toggle ${compressionEnabled ? 'active' : ''}`}
            onClick={handleToggleCompression}
            disabled={savingKey === 'compression_enabled'}
            role="switch"
            aria-checked={compressionEnabled}
          >
            <span className="profile-toggle-knob" />
          </button>
        </div>
      </div>
    </div>
  )
}
