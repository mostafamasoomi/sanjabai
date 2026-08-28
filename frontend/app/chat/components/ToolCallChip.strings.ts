import { dict } from '@/lib/i18n'
import type { Lang } from '@/components/LanguageToggle'

/* ═══════════════════════════════════════════════════════════════════════════
   ToolCallChip -- labels + the tool_call/tool_result reducer (P-B6, §ب‑۲).

   🚨 Product rule: regular users never see the provider, the route, or our
   internals -- and a raw backend tool name (`create_task`, `list_models`,
   ...) IS internals. `resolveToolChipLabel` is the one place that decides
   what text a chip shows, and it NEVER reads the server's own `label_fa`
   (an event's `label_fa` field is not even looked at anywhere in this
   product) and never falls back to the raw `name` -- only `KNOWN_TOOL_NAMES`
   below get a specific label; everything else gets the generic one.
   ═══════════════════════════════════════════════════════════════════════════ */

export type ToolChipStatus = 'running' | 'ok' | 'fail' | 'interrupted'

export type ToolCallEntry = {
  /** Raw backend tool name -- lookup key only, never rendered directly. */
  name: string
  status: ToolChipStatus
}

const FA = {
  generic: {
    running: 'در حال انجام یک عملیات…',
    ok: 'عملیات انجام شد',
    fail: 'عملیات ناموفق بود',
  },
  interrupted: 'ارتباط قطع شد؛ نتیجه نامشخص است',
  toolLabels: {
    create_task: {
      running: 'در حال ساخت وظیفه…',
      ok: 'وظیفه ساخته شد',
      fail: 'ساخت وظیفه ناموفق بود',
    },
    create_assistant: {
      running: 'در حال ساخت دستیار…',
      ok: 'دستیار ساخته شد',
      fail: 'ساخت دستیار ناموفق بود',
    },
    list_models: {
      running: 'در حال جستجوی مدل‌ها…',
      ok: 'فهرست مدل‌ها آماده شد',
      fail: 'جستجوی مدل‌ها ناموفق بود',
    },
  },
}

const EN: typeof FA = {
  generic: {
    running: 'Running an operation…',
    ok: 'Operation complete',
    fail: 'Operation failed',
  },
  interrupted: 'Connection lost; outcome unknown',
  toolLabels: {
    create_task: {
      running: 'Creating a task…',
      ok: 'Task created',
      fail: 'Failed to create the task',
    },
    create_assistant: {
      running: 'Creating an assistant…',
      ok: 'Assistant created',
      fail: 'Failed to create the assistant',
    },
    list_models: {
      running: 'Looking up models…',
      ok: 'Model list ready',
      fail: 'Failed to look up models',
    },
  },
}

export const toolCallChipStrings = dict(FA, EN)

/** The fixed client-side allow-list -- see the block comment above. Kept as
 *  the literal keys of `toolLabels` so a new tool can't get a label without
 *  also getting a translation on both sides of `dict()`. */
const KNOWN_TOOL_NAMES = Object.keys(FA.toolLabels) as (keyof typeof FA.toolLabels)[]

function isKnownToolName(name: string): name is keyof typeof FA.toolLabels {
  return (KNOWN_TOOL_NAMES as readonly string[]).includes(name)
}

/** The ONLY function allowed to turn a `ToolCallEntry` into visible text.
 *  `name` is used exclusively as a map lookup key here -- it is never
 *  interpolated into, concatenated with, or returned as part of any string. */
export function resolveToolChipLabel(name: string, status: ToolChipStatus, lang: Lang): string {
  const s = toolCallChipStrings(lang)
  if (status === 'interrupted') return s.interrupted
  const labels = isKnownToolName(name) ? s.toolLabels[name] : s.generic
  return labels[status]
}

/** Pure reducer for `tool_call`/`tool_result` SSE lines. Returns the SAME
 *  array reference when nothing changed (malformed event), so callers can
 *  skip a re-render. Never throws. */
export function applyToolCallEvent(calls: ToolCallEntry[], obj: any): ToolCallEntry[] {
  if (!obj || typeof obj !== 'object') return calls
  const name = typeof obj.name === 'string' ? obj.name : ''

  if (obj.type === 'tool_call') {
    return [...calls, { name, status: 'running' }]
  }

  if (obj.type === 'tool_result') {
    // `ok` must be EXACTLY `true` to render as success -- `false`, missing,
    // or any other truthy-but-not-boolean value renders as failed. Showing
    // a wrong-looking ✕ that the user can retry is far cheaper than showing
    // a false ✓ for an ambiguous result.
    const status: ToolChipStatus = obj.ok === true ? 'ok' : 'fail'
    // Match the most recent still-running call with this name -- a
    // duplicate/late/unmatched result is still shown rather than dropped.
    let idx = -1
    for (let i = calls.length - 1; i >= 0; i--) {
      if (calls[i].name === name && calls[i].status === 'running') { idx = i; break }
    }
    if (idx === -1) return [...calls, { name, status }]
    const next = calls.slice()
    next[idx] = { ...next[idx], status }
    return next
  }

  return calls
}

/** Disconnect-mid-loop case (§ب‑۲): a `tool_call` that never got its
 *  `tool_result` must end in a terminal, non-spinning chip. Returns the
 *  same reference when nothing was still running. */
export function finalizeToolCalls(calls: ToolCallEntry[]): ToolCallEntry[] {
  if (!calls.some(c => c.status === 'running')) return calls
  return calls.map(c => c.status === 'running' ? { ...c, status: 'interrupted' } : c)
}
