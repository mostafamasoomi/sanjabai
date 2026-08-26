import { toFaDigits } from '@/lib/format'
import { fmt } from '@/lib/i18n'
import type { Lang } from '@/components/LanguageToggle'

/* ═══════════════════════════════════════════════════════════════════════════
   Helpers
   Split out of page.tsx verbatim -- no behaviour change.

   Plain functions, not components or hooks, so each takes `lang` as a
   parameter (see the i18n spec note on non-component helpers) rather than
   reading it via useLang().
   ═══════════════════════════════════════════════════════════════════════════ */

export const fmtToman = (n: number, lang: Lang) => fmt(lang).price(n)
// No page-local money-formatter alias here -- call `fmt(lang).num` directly. A
// same-shaped wrapper named for the wrong currency used to live in this
// spot, and was one of the two places that habit caused a 10x display bug.
// Was `1.2M` / `34.0K` — Latin abbreviations that the RTL paragraph reorders
// away from their number. `fmt(lang).compact` gives the localized equivalent.
export const fmtTokens = (n: number, lang: Lang) => fmt(lang).compact(n)
export const fmtDate = (s: string | null, lang: Lang) => {
  if (!s) return '—'
  const d = new Date(s)
  if (lang === 'en') {
    return d.toLocaleDateString('en-GB', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }
  return toFaDigits(d.toLocaleDateString('fa-IR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }))
}
// `٪`/`%`: the localized formatter already picks the right sign and digits.
export const fmtPct = (n: number, lang: Lang) => fmt(lang).percent(n * 100, 1)

export const modelDisplayNames: Record<string, string> = {
  'agnes-2.0-flash': 'Agnes 2.0 Flash',
  'agnes-2.5-flash': 'Agnes 2.5 Flash',
  'gemini-3.5-flash': 'Gemini 3.5 Flash',
  'mimo-v2.5': 'MiMo V2.5',
  'mimo-v2.5-pro': 'MiMo V2.5 Pro',
  'mimo-v2.5-pro-ultraspeed': 'MiMo V2.5 Pro Ultra',
  'mistral-large': 'Mistral Large',
  'mistral-medium-3-5': 'Mistral Medium 3.5',
  'tencent-hy3': 'Tencent Hy3',
}

export const modelColors = [
  '#7c6df7', '#67e8f9', '#f59e0b', '#34d399', '#f87171',
  '#e879f9', '#60a5fa', '#fbbf24', '#a78bfa',
]

export const modelColor = (i: number) => modelColors[i % modelColors.length]
export const modelName = (m: string) => modelDisplayNames[m] || m
