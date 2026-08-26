// Relative, not `@/lib/i18n`: this file is transitively imported by
// tests/lib/upstreamOverhead.test.ts, a plain .ts file Vitest pulls straight
// into its module graph (not through Next's webpack/SWC resolver) — Vitest
// here has no `@` alias configured, so a value import through it fails at
// test time even though `tsc`/`next build` resolve it fine via tsconfig
// paths. The .strings.ts files that only ever get imported by a .tsx
// component (which Vitest never parses at all) don't hit this and use `@/`
// as normal — see CatalogFilterBar.strings.ts.
import { dict } from '@/lib/i18n'

/* Error strings for parseOverheadResponse (upstreamOverheadHelpers.ts). Split
   into its own dictionary rather than living inside the component's
   strings file: this file is plain .ts (no JSX, no `useLang`) so its own
   dictionary is read via a `lang` PARAMETER passed in by the caller, not the
   hook -- see the "not a component" note in upstreamOverheadHelpers.ts.

   `parseOverheadResponse(raw, lang)` defaults `lang` to 'fa' so the existing
   unit tests (tests/lib/upstreamOverhead.test.ts), which call it without a
   `lang` argument and assert on substrings like /stored/, /entries/ and
   /provider_default/, keep passing unchanged: those substrings are the raw
   backend field names and are kept literal in both languages below. */

const FA = {
  notObject: 'پاسخ سرور سربار یک شیء JSON نیست',
  missingStored: 'پاسخ سرور فاقد فیلد stored است — قرارداد بک‌اند تغییر کرده؟',
  entriesNotMap: 'فیلد stored.entries در پاسخ سرور یک نگاشت نیست',
  providerDefaultNotMap: 'فیلد stored.provider_default در پاسخ سرور یک نگاشت نیست',
  invalidOverheadForRoute: (routeKey: string) => `مقدار سربار برای مسیر «${routeKey}» عدد معتبر نیست`,
  invalidDefaultForProvider: (provider: string) => `مقدار پیش‌فرض سربار برای پروایدر «${provider}» عدد معتبر نیست`,
}

const EN: typeof FA = {
  notObject: 'The overhead response is not a JSON object',
  missingStored: 'The response is missing the stored field — has the backend contract changed?',
  entriesNotMap: 'stored.entries in the response is not a map',
  providerDefaultNotMap: 'stored.provider_default in the response is not a map',
  invalidOverheadForRoute: (routeKey) => `The overhead value for route "${routeKey}" is not a valid number`,
  invalidDefaultForProvider: (provider) => `The default overhead value for provider "${provider}" is not a valid number`,
}

export const upstreamOverheadHelperStrings = dict(FA, EN)
