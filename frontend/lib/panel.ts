/**
 * Consumer/developer panel preference.
 *
 * Backend context: `POST /admin/users/{uid}/panel` (backend/admin_user_ops.py)
 * writes `panel: 'consumer' | 'developer'` into the `users.preferences`
 * JSONB column, and `GET /api/auth/me` (backend/auth.py) returns the whole
 * `preferences` object back to the frontend. Until this module existed,
 * nothing read that value back -- the admin button saved and confirmed but
 * changed nothing. This is the single place that turns the stored value into
 * an actual UI decision. It is pure and has no side effects, so it is fully
 * unit-testable without mocking fetch/React.
 */

export type PanelPreference = 'consumer' | 'developer'

/**
 * Default when no valid preference is stored (missing/null/garbage).
 *
 * MUST stay 'developer'. Before this change, `/developer`, `/api-keys` and
 * `/hermes` were unconditionally visible to every authenticated user --
 * nothing has ever gated on `preferences.panel` before now. Defaulting to
 * 'consumer' would silently hide nav items from every existing user the
 * instant this ships, for a preference nobody has ever explicitly set. The
 * default must reproduce today's "show everything" behaviour exactly; only
 * a user an admin has actively moved to 'consumer' should see anything
 * hidden. See tests/lib/panel.test.ts for the behaviour-preservation proof.
 */
export const DEFAULT_PANEL: PanelPreference = 'developer'

const VALID_PANELS: readonly PanelPreference[] = ['consumer', 'developer']

/**
 * Reads `preferences.panel` out of an arbitrary/unknown value -- as it
 * arrives from `GET /api/auth/me`, or is simply absent -- and returns a
 * valid PanelPreference. Anything that isn't exactly the string 'consumer'
 * or 'developer' (undefined, null, a non-object, an array, a number, '',
 * an unrecognized string, ...) falls back to DEFAULT_PANEL rather than
 * throwing.
 */
export function getPanelPreference(preferences: unknown): PanelPreference {
  if (
    preferences === null ||
    preferences === undefined ||
    typeof preferences !== 'object' ||
    Array.isArray(preferences)
  ) {
    return DEFAULT_PANEL
  }
  const panel = (preferences as Record<string, unknown>).panel
  if (typeof panel === 'string' && (VALID_PANELS as readonly string[]).includes(panel)) {
    return panel as PanelPreference
  }
  return DEFAULT_PANEL
}

/**
 * Nav hrefs hidden from a user whose panel preference is 'consumer'. These
 * are the developer-oriented surfaces: the API docs page, API key
 * management, and the Hermes dev-server ordering flow. Everything else
 * (chat, wallet, pricing, dashboard, ...) is shared between both panels and
 * always stays visible. This is the one place to edit if the set of
 * developer-only surfaces ever changes.
 */
export const CONSUMER_HIDDEN_HREFS: readonly string[] = ['/developer', '/api-keys', '/hermes']

/**
 * Whether a nav item with the given href should be shown to a user with the
 * given panel preference.
 *
 * This is a display/UX decision only, not a security boundary -- see the
 * comment at the AppShell.tsx call site. A 'consumer' user typing the URL
 * directly still reaches the page; this function only controls whether the
 * nav *link* is rendered.
 */
export function isNavItemVisibleForPanel(href: string, panel: PanelPreference): boolean {
  if (panel === 'developer') return true
  return !CONSUMER_HIDDEN_HREFS.includes(href)
}
