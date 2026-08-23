/**
 * Detects when a streamed chat response was cut off by the model's
 * `max_tokens` ceiling rather than finishing naturally.
 *
 * Context: the upstream (LiteLLM -> Bynara) sends `finish_reason` on the
 * last SSE delta chunk. Verified live against the prod API container
 * (sanjab/gemini-3-flash, max_tokens=300, a prompt that reliably overruns
 * it): the value actually observed on this deployment is `"length"` --
 * the OpenAI-style value. `"max_tokens"` is kept as an accepted alias
 * since some upstreams/providers use that spelling instead; treating both
 * as truncation is strictly safer than only matching one.
 *
 * `null`/`undefined` (and any other value, e.g. `"stop"`) means either the
 * model finished on its own or we simply have no signal -- never surface
 * a "truncated" warning in that case, since a false positive is worse
 * than staying silent (see NEXT-SESSION brief: "سیگنال نداریم، نباید
 * هشدار الکی بدهیم").
 */

export type FinishReason = string | null | undefined

const TRUNCATION_FINISH_REASONS = new Set(['length', 'max_tokens'])

/** True when `finishReason` indicates the model hit its length ceiling. */
export function isLengthCappedFinish(finishReason: FinishReason): boolean {
  if (!finishReason) return false
  return TRUNCATION_FINISH_REASONS.has(finishReason)
}

export type TruncationStatus =
  | { truncated: false }
  | { truncated: true; empty: false }
  | { truncated: true; empty: true }

/**
 * Combines the finish-reason signal with the actual accumulated content to
 * decide what (if anything) to show the user.
 *
 * - Not length-capped -> { truncated: false } (nothing shown).
 * - Length-capped with visible content -> normal "ادامه بده" bar.
 * - Length-capped with zero/whitespace-only content -> the harsher
 *   zero-character case ("تلاش دوباره"), since the user paid for a
 *   response and got nothing at all.
 */
export function getTruncationStatus(finishReason: FinishReason, content: string): TruncationStatus {
  if (!isLengthCappedFinish(finishReason)) return { truncated: false }
  const empty = content.trim().length === 0
  return { truncated: true, empty }
}
