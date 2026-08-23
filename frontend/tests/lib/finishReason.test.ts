import { describe, it, expect } from 'vitest'

import { isLengthCappedFinish, getTruncationStatus } from '../../app/chat/finishReason'

/**
 * Unit tests for app/chat/finishReason.ts.
 *
 * Context: upstream sends `finish_reason` on the last SSE delta chunk when
 * a streamed chat response is cut off by the model's max_tokens ceiling.
 * Verified live against the prod API container (sanjab/gemini-3-flash,
 * max_tokens=300): the observed value is "length" (OpenAI-style). Some
 * upstreams/providers spell it "max_tokens" instead, so both are treated
 * as truncation. null/undefined/"stop" (or anything else) must never be
 * flagged -- no signal means no warning (a false "ناتمام ماند" banner is
 * worse than staying silent).
 */

describe('isLengthCappedFinish', () => {
  it('flags "length" as a length-capped finish', () => {
    expect(isLengthCappedFinish('length')).toBe(true)
  })

  it('flags "max_tokens" as a length-capped finish', () => {
    expect(isLengthCappedFinish('max_tokens')).toBe(true)
  })

  it('does not flag "stop" as a length-capped finish', () => {
    expect(isLengthCappedFinish('stop')).toBe(false)
  })

  it('does not flag null (no signal) as a length-capped finish', () => {
    expect(isLengthCappedFinish(null)).toBe(false)
  })

  it('does not flag undefined (no signal) as a length-capped finish', () => {
    expect(isLengthCappedFinish(undefined)).toBe(false)
  })
})

describe('getTruncationStatus', () => {
  it('"length" with content -> truncated, not empty', () => {
    expect(getTruncationStatus('length', 'یک متن ناتمام')).toEqual({ truncated: true, empty: false })
  })

  it('"max_tokens" with content -> truncated, not empty', () => {
    expect(getTruncationStatus('max_tokens', 'یک متن ناتمام')).toEqual({ truncated: true, empty: false })
  })

  it('"stop" -> not truncated regardless of content', () => {
    expect(getTruncationStatus('stop', 'یک متن کامل')).toEqual({ truncated: false })
  })

  it('null finish_reason -> not truncated (no signal, no false alarm)', () => {
    expect(getTruncationStatus(null, '')).toEqual({ truncated: false })
  })

  it('undefined finish_reason -> not truncated (no signal, no false alarm)', () => {
    expect(getTruncationStatus(undefined, 'برخی متن')).toEqual({ truncated: false })
  })

  it('length-capped + empty content -> the zero-character case', () => {
    expect(getTruncationStatus('length', '')).toEqual({ truncated: true, empty: true })
  })

  it('length-capped + whitespace-only content -> still the zero-character case', () => {
    expect(getTruncationStatus('length', '   \n  ')).toEqual({ truncated: true, empty: true })
  })
})
