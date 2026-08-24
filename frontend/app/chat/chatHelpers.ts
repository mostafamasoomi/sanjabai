import { faDate } from '@/lib/format'

export const PRESETS = [
  { icon: 'code' as const, label: 'کدنویسی', description: 'نوشتن و دیباگ کد', prompt: 'یک تابع در ' },
  { icon: 'chat' as const, label: 'ترجمه', description: 'ترجمه متن به فارسی', prompt: 'متن زیر را به فارسی روان ترجمه کن:\n\n' },
  { icon: 'search' as const, label: 'خلاصه‌سازی', description: 'خلاصه کردن متن طولانی', prompt: 'متن زیر را خلاصه کن:\n\n' },
  { icon: 'dashboard' as const, label: 'تحلیل', description: 'تحلیل دادهها و اطلاعات', prompt: 'داده‌های زیر را تحلیل کن:\n\n' },
]

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
   auto-enables search or auto-resends by itself. */
const SEARCH_INTENT_PATTERNS: RegExp[] = [
  /search\s+(the\s+)?(internet|web|online)/i,
  /google\s+(it|this|that)/i,
  /look\s+(it|this)?\s*up\s+online/i,
  /browse\s+the\s+web/i,
  /جستجو(ی)?\s*(در\s*)?(اینترنت|وب|آنلاین|نت|گوگل)/,
  /(اینترنت|نت|وب)\s*(رو|را)?\s*(جستجو|سرچ)/,
  /سرچ\s*(کن|بزن|بکن)/,
  /گوگل\s*(کن|بزن)/,
  /بگرد(ی)?\s*(تو|توی|در)?\s*(اینترنت|نت|وب)/,
]

export function hasSearchIntent(text: string): boolean {
  if (!text) return false
  return SEARCH_INTENT_PATTERNS.some(re => re.test(text))
}

/* ── Date formatting helper ──────────────────────────────────────────── */
export function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return 'اکنون'
    if (diffMins < 60) return `${diffMins} دقیقه پیش`
    if (diffHours < 24) return `${diffHours} ساعت پیش`
    if (diffDays < 7) return `${diffDays} روز پیش`
    // faDate normalises to Persian digits (raw toLocaleDateString leaks Latin
    // digits under small-icu); dateStr is already the ISO string faDate wants.
    return faDate(dateStr)
  } catch {
    return ''
  }
}

/* ── Date grouping helper ──────────────────────────────────────────────── */
export function getDateGroup(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    const now = new Date()
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const startOfYesterday = new Date(startOfToday.getTime() - 86400000)
    const startOfWeek = new Date(startOfToday.getTime() - startOfToday.getDay() * 86400000)
    if (d >= startOfToday) return 'امروز'
    if (d >= startOfYesterday) return 'دیروز'
    if (d >= startOfWeek) return 'این هفته'
    return 'قدیمی‌تر'
  } catch { return 'قدیمی‌تر' }
}
