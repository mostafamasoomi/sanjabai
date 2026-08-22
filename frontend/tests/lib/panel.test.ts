import { describe, it, expect } from 'vitest'

import {
  DEFAULT_PANEL,
  CONSUMER_HIDDEN_HREFS,
  getPanelPreference,
  isNavItemVisibleForPanel,
  type PanelPreference,
} from '../../lib/panel'

/**
 * Unit tests for lib/panel.ts -- the module that decides which nav items a
 * user with a given consumer/developer panel preference sees.
 *
 * Context: the admin "move user to developer panel" button writes
 * `preferences.panel` server-side (backend/admin_user_ops.py) but nothing
 * used to read it back -- the button confirmed success and changed nothing.
 * These tests are the behaviour-preservation proof for the fix, especially
 * the default: today every user (nobody has this preference set) sees the
 * full developer-oriented nav, so the default MUST be 'developer', not
 * 'consumer'.
 */

const ALL_NAV_HREFS = [
  '/chat', '/models', '/compare', '/status', '/dashboard', '/wallet',
  '/pricing', '/usage', '/api-keys', '/skills', '/hermes', '/assistants',
  '/memory', '/tasks', '/documents', '/images', '/developer', '/profile',
  '/referral', '/admin',
]

describe('panel', () => {
  // ── Default behaviour-preservation ─────────────────────────────────────
  describe('DEFAULT_PANEL', () => {
    it('is "developer" (preserves pre-fix behaviour of showing everything)', () => {
      expect(DEFAULT_PANEL).toBe('developer')
    })
  })

  describe('getPanelPreference default for missing/absent preference', () => {
    it('returns "developer" for undefined preferences', () => {
      expect(getPanelPreference(undefined)).toBe('developer')
    })

    it('returns "developer" for an empty preferences object (no panel key set)', () => {
      expect(getPanelPreference({})).toBe('developer')
    })

    it('returns "developer" for a preferences object with unrelated keys only', () => {
      expect(getPanelPreference({ ai_personality: 'friendly', theme: 'dark' })).toBe('developer')
    })
  })

  // ── Garbage handling ────────────────────────────────────────────────────
  describe('getPanelPreference defensive fallback on garbage input', () => {
    it('falls back to the default for null', () => {
      expect(getPanelPreference(null)).toBe(DEFAULT_PANEL)
    })

    it('falls back to the default for a non-object (string)', () => {
      expect(getPanelPreference('developer')).toBe(DEFAULT_PANEL)
    })

    it('falls back to the default for a non-object (number)', () => {
      expect(getPanelPreference(42)).toBe(DEFAULT_PANEL)
    })

    it('falls back to the default for an array', () => {
      expect(getPanelPreference(['consumer'])).toBe(DEFAULT_PANEL)
    })

    it('falls back to the default when panel is a number', () => {
      expect(getPanelPreference({ panel: 1 })).toBe(DEFAULT_PANEL)
    })

    it('falls back to the default when panel is an empty string', () => {
      expect(getPanelPreference({ panel: '' })).toBe(DEFAULT_PANEL)
    })

    it('falls back to the default when panel is an unknown string', () => {
      expect(getPanelPreference({ panel: 'admin' })).toBe(DEFAULT_PANEL)
    })

    it('falls back to the default when panel is null', () => {
      expect(getPanelPreference({ panel: null })).toBe(DEFAULT_PANEL)
    })

    it('does not throw for any of the above', () => {
      const garbage: unknown[] = [undefined, null, 'x', 42, [], {}, { panel: {} }, { panel: [] }]
      for (const g of garbage) {
        expect(() => getPanelPreference(g)).not.toThrow()
      }
    })
  })

  // ── Valid values pass through ───────────────────────────────────────────
  describe('getPanelPreference with a valid stored value', () => {
    it('returns "consumer" when explicitly set', () => {
      expect(getPanelPreference({ panel: 'consumer' })).toBe('consumer')
    })

    it('returns "developer" when explicitly set', () => {
      expect(getPanelPreference({ panel: 'developer' })).toBe('developer')
    })

    it('reads panel alongside other unrelated preference keys', () => {
      expect(getPanelPreference({ theme: 'dark', panel: 'consumer' })).toBe('consumer')
    })
  })

  // ── Nav visibility: consumer hides exactly the intended hrefs ─────────
  describe('isNavItemVisibleForPanel with "consumer"', () => {
    it('hides exactly /developer, /api-keys, /hermes and nothing else', () => {
      const hidden = ALL_NAV_HREFS.filter((h) => !isNavItemVisibleForPanel(h, 'consumer'))
      expect(hidden.sort()).toEqual([...CONSUMER_HIDDEN_HREFS].sort())
      expect(hidden.sort()).toEqual(['/api-keys', '/developer', '/hermes'].sort())
    })

    it('keeps every other nav item visible', () => {
      const visible = ALL_NAV_HREFS.filter((h) => isNavItemVisibleForPanel(h, 'consumer'))
      for (const h of CONSUMER_HIDDEN_HREFS) expect(visible).not.toContain(h)
      expect(visible).toContain('/chat')
      expect(visible).toContain('/wallet')
      expect(visible).toContain('/admin')
    })
  })

  // ── Nav visibility: developer hides nothing ─────────────────────────────
  describe('isNavItemVisibleForPanel with "developer"', () => {
    it('hides nothing across the whole real nav list', () => {
      for (const href of ALL_NAV_HREFS) {
        expect(isNavItemVisibleForPanel(href, 'developer')).toBe(true)
      }
    })

    it('shows the developer-only items too', () => {
      expect(isNavItemVisibleForPanel('/developer', 'developer')).toBe(true)
      expect(isNavItemVisibleForPanel('/api-keys', 'developer')).toBe(true)
      expect(isNavItemVisibleForPanel('/hermes', 'developer')).toBe(true)
    })
  })

  // ── End-to-end: default preference behaves like "developer" ────────────
  describe('end-to-end default behaviour', () => {
    it('a user with no stored preference sees the same nav as an explicit "developer" user', () => {
      const resolvedFromMissing: PanelPreference = getPanelPreference(undefined)
      for (const href of ALL_NAV_HREFS) {
        expect(isNavItemVisibleForPanel(href, resolvedFromMissing)).toBe(
          isNavItemVisibleForPanel(href, 'developer'),
        )
      }
    })
  })
})
