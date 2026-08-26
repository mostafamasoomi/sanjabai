import type { Lang } from '@/components/LanguageToggle'
import { fmt, dict } from '@/lib/i18n'
import { chatHelpersStrings } from './chatHelpers.strings'
import type { Message } from './chatTypes'

/** The synthetic first bubble shown in a brand-new / just-cleared chat.
 *  A plain function (not a component) so both page.tsx (has `lang` via
 *  useLang) and useConversations.ts (a hook, receives `lang` as a param)
 *  can build the same shape without duplicating the Persian/English copy. */
export function makeWelcomeMessage(lang: Lang): Message {
  return { id: 'welcome', role: 'assistant', content: chatHelpersStrings(lang).welcomeMessage }
}

/** Not a component -- takes `lang` as a plain parameter (see useChatStream/
 *  page.tsx call sites) instead of calling the useLang() hook. */
export function getPresets(lang: Lang) {
  const s = chatHelpersStrings(lang)
  return [
    { icon: 'code' as const, ...s.presetCode },
    { icon: 'chat' as const, ...s.presetTranslate },
    { icon: 'search' as const, ...s.presetSummarize },
    { icon: 'dashboard' as const, ...s.presetAnalyze },
  ]
}

// walletBalance is raw Toman (see backend/wallet.py, GET /wallet) — the
// threshold below and the <Num> that renders the same value must agree on
// that unit, so name it here instead of repeating the bare literal.
export const LOW_BALANCE_TOMAN = 5000

export function generateId() { return Date.now().toString(36) + Math.random().toString(36).slice(2) }

/* ── Search-intent detection ──────────────────────────────────────────
   The web-search feature only ever fires from the globe toggle (default
   OFF), so a user typing "search the internet" in plain language sees
   nothing happen. This is a lightweight, no-dependency heuristic used only
   to offer an inline hint to turn the toggle on and re-send -- it never
   auto-enables search or auto-resends by itself.

   Bilingual lookup table, not a translation: a user can phrase this request
   in either language regardless of which one the panel is currently
   showing, so BOTH pattern sets are tested together on every call -- see
   hasSearchIntent below. Structured through dict() (same shape as any
   Foo.strings.ts) purely so the two pattern sets sit side by side with the
   same completeness guarantee as everything else in this codebase, not
   because either half is only used in one language. */
const SEARCH_INTENT_PATTERNS_FA = {
  patterns: [
    /جستجو(ی)?\s*(در\s*)?(اینترنت|وب|آنلاین|نت|گوگل)/,
    /(اینترنت|نت|وب)\s*(رو|را)?\s*(جستجو|سرچ)/,
    /سرچ\s*(کن|بزن|بکن)/,
    /گوگل\s*(کن|بزن)/,
    /بگرد(ی)?\s*(تو|توی|در)?\s*(اینترنت|نت|وب)/,
  ],
}
const SEARCH_INTENT_PATTERNS_EN: typeof SEARCH_INTENT_PATTERNS_FA = {
  patterns: [
    /search\s+(the\s+)?(internet|web|online)/i,
    /google\s+(it|this|that)/i,
    /look\s+(it|this)?\s*up\s+online/i,
    /browse\s+the\s+web/i,
  ],
}
const searchIntentPatterns = dict(SEARCH_INTENT_PATTERNS_FA, SEARCH_INTENT_PATTERNS_EN)

export function hasSearchIntent(text: string): boolean {
  if (!text) return false
  const all = [...searchIntentPatterns('fa').patterns, ...searchIntentPatterns('en').patterns]
  return all.some(re => re.test(text))
}

/* ── Date formatting helper ──────────────────────────────────────────── */
export function formatDate(dateStr: string, lang: Lang): string {
  const s = chatHelpersStrings(lang)
  try {
    const d = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return s.justNow
    if (diffMins < 60) return s.minutesAgo(diffMins)
    if (diffHours < 24) return s.hoursAgo(diffHours)
    if (diffDays < 7) return s.daysAgo(diffDays)
    // f.date normalises the numerals for the language (faDate emits Persian
    // digits, enDate Latin ones); dateStr is already the ISO string it wants.
    return fmt(lang).date(dateStr)
  } catch {
    return ''
  }
}

/* ── Date grouping helper ──────────────────────────────────────────────── */
// Language-independent so callers (useConversations' groupedConversations)
// can key a Record by it without re-deriving the group from a translated
// string; ConversationSidebar renders the label via dateGroupLabel below.
export type DateGroupKey = 'today' | 'yesterday' | 'week' | 'older'

export function getDateGroup(dateStr: string): DateGroupKey {
  try {
    const d = new Date(dateStr)
    const now = new Date()
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const startOfYesterday = new Date(startOfToday.getTime() - 86400000)
    const startOfWeek = new Date(startOfToday.getTime() - startOfToday.getDay() * 86400000)
    if (d >= startOfToday) return 'today'
    if (d >= startOfYesterday) return 'yesterday'
    if (d >= startOfWeek) return 'week'
    return 'older'
  } catch { return 'older' }
}

export function dateGroupLabel(key: DateGroupKey, lang: Lang): string {
  const s = chatHelpersStrings(lang)
  const map: Record<DateGroupKey, string> = {
    today: s.groupToday,
    yesterday: s.groupYesterday,
    week: s.groupThisWeek,
    older: s.groupOlder,
  }
  return map[key]
}
