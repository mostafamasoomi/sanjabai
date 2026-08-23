/**
 * Framework-agnostic accumulator for streamed SSE chat tokens.
 *
 * Bug fixed: chat/page.tsx used to call setMessages() on every single SSE
 * `delta` token while streaming. Each call re-rendered ChatMessageItem and
 * made MarkdownRenderer re-parse the ENTIRE accumulated response from
 * scratch (remark -> sanitize -> highlight) on every token -- O(n^2) over a
 * long response, plus a visibly janky UI.
 *
 * StreamAccumulator batches many push() calls that arrive faster than the
 * scheduler fires into a single onFlush call. The accumulated text (`acc`)
 * is always updated synchronously inside push() -- only the RATE of
 * onFlush (i.e. the setMessages call in page.tsx) is throttled, so no
 * chunk can ever be delayed into oblivion. Callers MUST invoke flushNow()
 * once after the stream ends ([DONE] / reader done) so the last, possibly
 * still-pending batch reaches the UI.
 *
 * Deliberately NOT a React hook: page.tsx creates one instance per call to
 * sendMessage() inside an async function, and React hooks cannot be called
 * outside the render phase (useStreamAccumulator() could not legally run
 * inside an async event-handler body anyway).
 *
 * Tests: frontend/tests/lib/stream-accumulate.test.ts -- asserts the
 * flushed text is byte-for-byte equal to chunks.join('') after N chunks +
 * a final flushNow(), and that a chunk arriving after the last scheduled
 * flush already fired is still present after the mandatory final flush.
 */

export interface FlushScheduler {
  schedule(cb: () => void): number
  cancel(handle: number): void
}

/** Real-world scheduler: requestAnimationFrame in a browser (batches to
 *  screen refresh rate, ~60fps), a ~50ms setTimeout everywhere else (SSR /
 *  vitest / environments without rAF). 50-80ms was the range suggested for
 *  a fixed-interval fallback; 50ms is picked to stay comfortably under the
 *  point a human perceives as "stalled" while still cutting re-renders by
 *  1-2 orders of magnitude on a fast stream. */
export function createRafScheduler(intervalMs = 50): FlushScheduler {
  const hasRaf = typeof requestAnimationFrame === 'function' && typeof cancelAnimationFrame === 'function'
  if (hasRaf) {
    return {
      schedule: (cb) => requestAnimationFrame(cb) as unknown as number,
      cancel: (handle) => cancelAnimationFrame(handle),
    }
  }
  return {
    schedule: (cb) => setTimeout(cb, intervalMs) as unknown as number,
    cancel: (handle) => clearTimeout(handle as unknown as ReturnType<typeof setTimeout>),
  }
}

export class StreamAccumulator {
  private acc = ''
  private pendingHandle: number | null = null

  constructor(
    private readonly onFlush: (text: string) => void,
    private readonly scheduler: FlushScheduler = createRafScheduler(),
  ) {}

  /** Append a chunk and (re)schedule a throttled flush. Never drops or
   *  reorders text: `acc` is updated synchronously here, only the onFlush
   *  callback is delayed/coalesced. */
  push(chunk: string): void {
    if (!chunk) return
    this.acc += chunk
    if (this.pendingHandle === null) {
      this.pendingHandle = this.scheduler.schedule(() => {
        this.pendingHandle = null
        this.onFlush(this.acc)
      })
    }
  }

  /** Cancel any pending scheduled flush WITHOUT invoking onFlush. Used on
   *  the upstream-error path in page.tsx, which sets the final bubble
   *  content itself (acc + the error message) -- a stale scheduled flush
   *  firing afterwards would otherwise overwrite that with acc alone. */
  cancel(): void {
    if (this.pendingHandle !== null) {
      this.scheduler.cancel(this.pendingHandle)
      this.pendingHandle = null
    }
  }

  /** Synchronous, immediate flush. MUST be called once after the stream
   *  ends ([DONE] / reader done) so the last batch of tokens -- which may
   *  postdate the last scheduled flush -- reaches the UI. */
  flushNow(): void {
    this.cancel()
    this.onFlush(this.acc)
  }

  /** Current accumulated text: the single source of truth, always up to
   *  date synchronously and independent of whether onFlush has fired yet. */
  getText(): string {
    return this.acc
  }
}

export function createStreamAccumulator(
  onFlush: (text: string) => void,
  scheduler?: FlushScheduler,
): StreamAccumulator {
  return new StreamAccumulator(onFlush, scheduler)
}
