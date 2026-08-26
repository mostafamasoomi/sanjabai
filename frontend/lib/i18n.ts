/* ═══════════════════════════════════════════════════════════════════════════
   The product's translation contract.

   Two problems, both solved here so every screen solves them the same way.
   Started life as the admin panel's; the landing page and the user-facing app
   use the identical shape, so it is not admin-specific and no longer named
   as though it were.

   ── 1. Completeness is checked by the compiler, not by reading ─────────────

   A dictionary is a pair of plain objects and one type annotation:

       const FA = {
         title: 'عملیات کاتالوگ مدل‌ها',
         selected: (n: string) => `${n} مدل انتخاب شده`,
       }
       const EN: typeof FA = {
         title: 'Model Catalog Operations',
         selected: (n) => `${n} model${n === '1' ? '' : 's'} selected`,
       }
       export const catalogStrings = dict(FA, EN)

   `EN: typeof FA` is the whole trick. Because FA is declared WITHOUT
   `as const`, its inferred type is `{ title: string; selected: (n: string)
   => string }` — a shape, not literals — so annotating EN with it makes a
   missing key, a typo'd key, an extra key, or a string where a function
   belongs into a compile error. Across 1,168 strings that is the only
   completeness check that can actually be trusted; nobody is going to
   eyeball two 60-key objects and be sure.

   Do NOT write `as const` on FA. It would make every value a literal type
   and EN could then only ever equal the Persian text.

   ── 2. Numbers and dates are Persian by construction ───────────────────────

   lib/format.tsx is deliberately opinionated: `faNum` always emits Persian
   digits, `faPrice` always appends «تومان», `faCompact` appends «هزار». That
   is correct for a Persian-first product and wrong the moment the panel is
   in English — `1,153 models` reading as `۱٬۱۵۳ models` is not translated,
   it is half-translated. `fmt(lang)` returns the same family of helpers
   bound to a language, so a section formats through `f.num(...)` and gets
   the right numerals without deciding anything.

   Money stays raw integer toman end to end (see lib/format.tsx). `f.price`
   changes the numerals and the unit word, never the value.
   ═══════════════════════════════════════════════════════════════════════════ */

import type { Lang } from '@/components/LanguageToggle'
import { faNum, faPrice, faCompact, faPercent, faDate, faTime, type NumOptions } from './format'

/** Binds a Persian/English pair into a `(lang) => strings` reader.
 *
 *  Sections call it once per render: `const s = catalogStrings(lang)`. */
export function dict<T extends Record<string, unknown>>(fa: T, en: T) {
  return (lang: Lang): T => (lang === 'en' ? en : fa)
}

/* ── English counterparts of the format.tsx helpers ────────────────────────
   Latin digits, `,` for thousands, `.` for the decimal mark. Kept next to
   the Persian ones rather than inside format.tsx so that file stays the
   single statement of the PERSIAN policy and does not grow a second one. */

function enNum(
  value: number | null | undefined,
  { fallback = '—', decimals = 0, signed = false }: NumOptions = {},
): string {
  if (value == null || !Number.isFinite(value)) return fallback
  const fixed = Math.abs(value).toFixed(decimals)
  const [whole, fraction] = fixed.split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const body = fraction ? `${grouped}.${fraction}` : grouped
  // A real minus, matching faNum — it keeps its shape next to digits.
  const sign = value < 0 ? '−' : signed && value > 0 ? '+' : ''
  return sign + body
}

function enPrice(value: number | null | undefined, options?: NumOptions): string {
  const n = enNum(value, options)
  return n === (options?.fallback ?? '—') ? n : `${n} Toman`
}

function enCompact(value: number | null | undefined, fallback = '—'): string {
  if (value == null || !Number.isFinite(value)) return fallback
  const abs = Math.abs(value)
  if (abs >= 1_000_000) {
    return `${enNum(value / 1_000_000, { decimals: abs % 1_000_000 === 0 ? 0 : 1 })}M`
  }
  if (abs >= 1_000) {
    return `${enNum(value / 1_000, { decimals: abs % 1_000 === 0 ? 0 : 1 })}K`
  }
  return enNum(value)
}

function enPercent(value: number | null | undefined, decimals = 0, fallback = '—'): string {
  const n = enNum(value, { decimals, fallback })
  return n === fallback ? n : `${n}%`
}

function enDate(iso: string | null | undefined, fallback = '—'): string {
  if (!iso) return fallback
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return fallback
  return d.toLocaleDateString('en-GB', { year: 'numeric', month: 'short', day: 'numeric' })
}

function enTime(iso: string | null | undefined, fallback = '—'): string {
  if (!iso) return fallback
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return fallback
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

export interface Formatters {
  num: (value: number | null | undefined, options?: NumOptions) => string
  price: (value: number | null | undefined, options?: NumOptions) => string
  compact: (value: number | null | undefined, fallback?: string) => string
  percent: (value: number | null | undefined, decimals?: number, fallback?: string) => string
  date: (iso: string | null | undefined, fallback?: string) => string
  time: (iso: string | null | undefined, fallback?: string) => string
}

const FA_FMT: Formatters = {
  num: faNum, price: faPrice, compact: faCompact,
  percent: faPercent, date: faDate, time: faTime,
}
const EN_FMT: Formatters = {
  num: enNum, price: enPrice, compact: enCompact,
  percent: enPercent, date: enDate, time: enTime,
}

/** The number/date helpers for a language. Stable identities, so this is safe
 *  in a dependency array. */
export function fmt(lang: Lang): Formatters {
  return lang === 'en' ? EN_FMT : FA_FMT
}

/** `dir` for a container whose text is now translated.
 *
 *  Admin sections used to hard-code `dir="rtl"` because their content was
 *  Persian regardless. Once a section is translated that attribute is a bug:
 *  English text in a right-to-left box puts the labels, icons and table
 *  columns on the wrong side. A translated section either drops `dir`
 *  entirely — inheriting from the panel root, which follows the language —
 *  or uses this when it needs to be explicit.
 *
 *  `dir="ltr"` on a model id or a raw error code stays: those are Latin
 *  strings in either language and have nothing to do with the UI direction. */
export function dirFor(lang: Lang): 'rtl' | 'ltr' {
  return lang === 'en' ? 'ltr' : 'rtl'
}

/** The refusal text from a failed API response body, in the active language.
 *
 *  The backend answers `{"detail": "<fa>", "detail_en": "<en>"}` — the Persian
 *  key keeps its original name and value so nothing that read it before
 *  notices, and the English is a sibling (backend/i18n.py explains why both
 *  travel together instead of the server picking one). A body that predates
 *  that change, or an endpoint not yet converted, has no `detail_en`; falling
 *  back to the Persian is correct — the server's explanation of what went
 *  wrong is worth more than a generic English sentence.
 *
 *  The OpenAI-compatible routes nest their text under `error.message`
 *  instead; the same sibling convention applies there. */
export function detailFor(body: unknown, lang: Lang): string | null {
  if (!body || typeof body !== 'object') return null
  const b = body as Record<string, unknown>
  const pickPair = (fa: unknown, en: unknown): string | null => {
    if (lang === 'en' && typeof en === 'string' && en.trim()) return en.trim()
    return typeof fa === 'string' && fa.trim() ? fa.trim() : null
  }
  const detail = pickPair(b.detail, b.detail_en)
  if (detail) return detail
  const nested = b.error as Record<string, unknown> | undefined
  if (nested && typeof nested === 'object') {
    return pickPair(nested.message, nested.message_en)
  }
  return null
}
