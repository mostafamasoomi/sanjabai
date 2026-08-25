/* Extracting the backend's own explanation out of a failed admin response.
 *
 * Lives in its own file rather than inside AdminPanel.tsx because that file is
 * already 970+ lines, well over this project's 500-line cap, and the standing
 * rule is that new things go in new files instead of growing it further.
 *
 * The bug this closes: AdminPanel's `api()` threw `خطای سرور (400)` the moment
 * it saw a non-2xx status, *before* any caller could read the response body.
 * Every admin endpoint in this codebase refuses with a Persian `detail`
 * (FastAPI's convention — e.g. "upstream نامعتبر، گزینه‌های معتبر: ...") and
 * that one sentence, the only thing that says what was actually wrong, was
 * thrown away every single time. The admin saw "the server said no" and
 * nothing else.
 */

import { getLang } from '@/components/LanguageToggle'

/** The generic fallback shown when the response carries no usable message.
 *
 *  Reads the language with `getLang()` rather than the `useLang()` hook: this
 *  runs inside `api()`, in an async request path, not during a render. It is
 *  a plain localStorage read and is legal anywhere.
 *
 *  NOTE the honest limit here. The *backend's* own refusals are Persian
 *  (FastAPI `detail`, e.g. «upstream نامعتبر، گزینه‌های معتبر: …») and this
 *  function deliberately prefers them — that sentence is the only thing that
 *  says what actually went wrong. So an English panel still surfaces a
 *  Persian message when the server explains itself. Translating those means
 *  translating the API, which is a backend change and not this one. */
export function genericError(status: number): string {
  return getLang() === 'en' ? `Server error (${status})` : `خطای سرور (${status})`
}

/** Best available human-readable Persian message for a failed response.
 *
 *  Reads the body with `text()` rather than `json()` on purpose: an error
 *  response is not guaranteed to be JSON at all (a proxy 502, an HTML error
 *  page, an empty body), and `res.json()` on that throws a *parse* error that
 *  would mask the real HTTP failure. Anything unparseable, or a body with no
 *  usable string, falls back to the generic status message rather than
 *  surfacing raw HTML to the admin.
 *
 *  Consuming the body here is safe: the only caller throws immediately
 *  afterwards, so no code ever gets the chance to read the stream again.
 */
export async function errorDetail(res: Response): Promise<string> {
  const generic = genericError(res.status)
  let raw = ''
  try {
    raw = await res.text()
  } catch {
    return generic
  }
  if (!raw.trim()) return generic

  let body: unknown
  try {
    body = JSON.parse(raw)
  } catch {
    return generic
  }
  if (!body || typeof body !== 'object') return generic

  // FastAPI's own refusals use `detail`. The OpenAI-compatible routes
  // (/v1/chat/completions, /v1/images/generations) nest the text under
  // `error.message` instead. Accept either shape; ignore anything else.
  const detail = (body as { detail?: unknown }).detail
  if (typeof detail === 'string' && detail.trim()) return detail.trim()

  // FastAPI request-validation errors put a *list* of objects in `detail`.
  // Those carry `msg` strings that are English pydantic text, not something
  // to show an admin — so they deliberately fall through to the generic
  // message rather than leaking "value is not a valid integer" into the UI.

  const message = (body as { error?: { message?: unknown } }).error?.message
  if (typeof message === 'string' && message.trim()) return message.trim()

  return generic
}
