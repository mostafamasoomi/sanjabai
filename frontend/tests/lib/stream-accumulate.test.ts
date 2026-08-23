import { describe, it, expect } from 'vitest'

import { StreamAccumulator, type FlushScheduler } from '../../app/chat/useStreamAccumulator'

/**
 * Unit tests for StreamAccumulator (app/chat/useStreamAccumulator.ts).
 *
 * Context: chat/page.tsx used to call setMessages() on every single SSE
 * `delta` token while streaming, which re-rendered ChatMessageItem and made
 * MarkdownRenderer re-parse the ENTIRE accumulated response from scratch on
 * every token (remark -> sanitize -> highlight) -- O(n^2) over a long
 * response, and a visibly janky UI. StreamAccumulator batches push() calls
 * that arrive faster than the scheduler fires into a single onFlush call,
 * without ever touching the accumulated text itself: `acc` is appended to
 * synchronously in push(), so no chunk can be delayed into oblivion -- only
 * the rate of onFlush (i.e. setMessages) calls is throttled.
 *
 * These tests use a manual (non-real-time) FlushScheduler double so they run
 * instantly and deterministically -- no fake timers, no rAF polyfill, no
 * jsdom (this repo's vitest has no environment/jsx transform configured; see
 * tests/lib/upstreamOverhead.test.ts for why .tsx files can't be tested here
 * at all -- this module is plain .ts specifically so it can be).
 */

/** A scheduler double that never fires on its own -- `schedule()` just
 *  records the callback so the test can assert nothing was flushed until
 *  flushNow()/a manual fire is triggered. Mirrors a burst of chunks arriving
 *  faster than a single animation frame. */
function createManualScheduler(): FlushScheduler & { pending: (() => void)[]; fireAll: () => void } {
  const pending: (() => void)[] = []
  let nextHandle = 1
  const handles = new Map<number, () => void>()
  return {
    pending,
    schedule(cb) {
      const handle = nextHandle++
      handles.set(handle, cb)
      pending.push(cb)
      return handle
    },
    cancel(handle) {
      const cb = handles.get(handle)
      if (cb) {
        handles.delete(handle)
        const idx = pending.indexOf(cb)
        if (idx >= 0) pending.splice(idx, 1)
      }
    },
    fireAll() {
      // Fire whatever is currently pending (mirrors a real rAF/timeout tick).
      const toFire = pending.splice(0, pending.length)
      for (const cb of toFire) cb()
    },
  }
}

/** A scheduler double that fires synchronously and immediately on every
 *  schedule() call -- mirrors the worst case where every push() happens to
 *  land in its own animation frame (still must not lose/reorder anything). */
function createImmediateScheduler(): FlushScheduler {
  return {
    schedule(cb) {
      cb()
      return 0
    },
    cancel() {
      /* nothing to cancel -- schedule() already ran synchronously */
    },
  }
}

describe('StreamAccumulator', () => {
  it('accumulates 500 chunks and the final flushed text is byte-for-byte equal to chunks.join(\'\')', () => {
    const chunks = Array.from({ length: 500 }, (_, i) => `chunk-${i}-سلام${i % 7 === 0 ? '\n' : ''}`)
    const expected = chunks.join('')

    const flushes: string[] = []
    const acc = new StreamAccumulator((text) => flushes.push(text), createImmediateScheduler())

    for (const c of chunks) acc.push(c)
    // Mandatory final flush after [DONE] -- must be called regardless of
    // whether a scheduled flush already fired for the very last chunk.
    acc.flushNow()

    expect(acc.getText()).toBe(expected)
    expect(flushes[flushes.length - 1]).toBe(expected)
    // No chunk was ever dropped or reordered along the way either -- every
    // intermediate flush must be a prefix of the final text.
    for (const f of flushes) {
      expect(expected.startsWith(f)).toBe(true)
    }
  })

  it('does not lose the last chunk when it arrives after the last scheduled flush already fired', () => {
    const chunks = ['سلام ', 'دنیا', '!', ' پایانی']
    const expected = chunks.join('')

    const scheduler = createManualScheduler()
    const flushes: string[] = []
    const acc = new StreamAccumulator((text) => flushes.push(text), scheduler)

    // First three chunks arrive, then the scheduled flush actually fires
    // (simulating an animation frame boundary) -- captures a PARTIAL text.
    acc.push(chunks[0])
    acc.push(chunks[1])
    acc.push(chunks[2])
    scheduler.fireAll()
    expect(flushes).toEqual([chunks.slice(0, 3).join('')])

    // The final chunk arrives AFTER that flush fired (pendingHandle is null
    // again), then the stream ends ([DONE]) and the mandatory final flush
    // runs. If the last chunk were only queued but never flushed, this
    // would be the exact bug: the UI (and the saved conversation) would be
    // missing the tail of the response.
    acc.push(chunks[3])
    acc.flushNow()

    expect(acc.getText()).toBe(expected)
    expect(flushes[flushes.length - 1]).toBe(expected)
  })

  it('cancel() drops a pending scheduled flush without invoking onFlush (upstream-error path)', () => {
    const scheduler = createManualScheduler()
    const flushes: string[] = []
    const acc = new StreamAccumulator((text) => flushes.push(text), scheduler)

    acc.push('partial')
    acc.cancel()
    scheduler.fireAll() // the cancelled callback must not still be pending
    expect(flushes).toEqual([])
    expect(acc.getText()).toBe('partial')
  })
})
