/**
 * Central fetch wrapper for browser-side calls to the Sanjabai backend.
 *
 * WHY THIS EXISTS — do not delete this as "pointless boilerplate".
 *
 * `backend/security.py`'s `CsrfMiddleware` rejects any non-safe-method
 * request (POST/PUT/PATCH/DELETE/...) to a path under `/auth/`,
 * `/api-keys`, `/referral/`, or `/v1/rag/` with a 403 whenever the request
 * carries a `session` cookie (`SESSION_COOKIE_NAME` in
 * `backend/dependencies.py`) — UNLESS the request also carries an
 * `X-Requested-With` header. A cross-site `<form>` submit forged by an
 * attacker can ride the browser's ambient session cookie, but it cannot
 * add a custom header — only same-origin `fetch`/`XHR` code can. That is
 * the whole CSRF defence, and it is live in production, not dead code.
 *
 * Every mutating call from this frontend to `/api/...` or `/v1/...` MUST
 * go through `apiFetch` (or otherwise set the header itself), or it will
 * be rejected by the backend with a Persian 403 once the user has a
 * session cookie — which happens for every logged-in user, since
 * `/api/auth/login` sets one as a fallback alongside the localStorage
 * token. See docs / session notes for the incident this fixed.
 *
 * GET/HEAD/OPTIONS are left alone on purpose: the backend does not gate
 * safe methods, and adding a custom header to them would force an extra
 * CORS preflight for zero benefit.
 */

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

/**
 * Normalize any HeadersInit shape (plain object, array of pairs, or a
 * Headers instance) into a mutable Headers object. Using the Headers
 * constructor directly (rather than `{ ...init.headers }`) is required —
 * a naive object spread silently drops all entries when `init.headers`
 * is already a Headers instance, since Headers stores its data on
 * internal slots, not enumerable own properties.
 */
function normalizeHeaders(init?: HeadersInit): Headers {
  return new Headers(init)
}

/**
 * Drop-in replacement for `fetch` that adds `X-Requested-With` on
 * non-safe methods so the backend CSRF middleware accepts the request.
 * Everything else (credentials, body, signal, caller headers, ...) is
 * passed through unchanged. A caller that already set the header wins —
 * this never overwrites an explicit value.
 */
export function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const method = (init.method || 'GET').toUpperCase()
  const headers = normalizeHeaders(init.headers)

  if (!SAFE_METHODS.has(method) && !headers.has('X-Requested-With')) {
    headers.set('X-Requested-With', 'XMLHttpRequest')
  }

  return fetch(input, { ...init, headers })
}
