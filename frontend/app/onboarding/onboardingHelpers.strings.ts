import { dict } from '@/lib/i18n'

/* `lib/useCatalog.ts`'s `PRICE_BAND_LABEL` (imported via `priceBand()`'s
   return value, not its Persian label) is Persian-only and out of this
   batch's scope (lib/**) -- reported to the senior as a backend/shared-file
   follow-up. `priceBand` (the band-computing function) is still imported
   from there; only its text label is re-done here, bilingually, so the
   onboarding flow doesn't leak an unconditional Persian badge into the
   English UI. */

const FA = {
  priceBand: { standard: 'استاندارد', premium: 'حرفه‌ای' } as Record<'standard' | 'premium', string>,
  currency: (code: string) => (code === 'IRT' ? 'تومان' : code === 'IRR' ? 'ریال' : code),
  perMillionTokens: (input: string, output: string, cur: string) =>
    `هر ۱ میلیون توکن — ورودی ${input} · خروجی ${output} ${cur}`,
  inputOutputShort: (input: string, output: string, cur: string) => `ورودی ${input} · خروجی ${output} ${cur}`,
  tokens: (n: string) => `${n} توکن`,
}

const EN: typeof FA = {
  priceBand: { standard: 'Standard', premium: 'Pro' },
  currency: (code) => (code === 'IRT' ? 'Toman' : code === 'IRR' ? 'Rial' : code),
  perMillionTokens: (input, output, cur) => `Per 1M tokens — in ${input} · out ${output} ${cur}`,
  inputOutputShort: (input, output, cur) => `In ${input} · out ${output} ${cur}`,
  tokens: (n) => `${n} tokens`,
}

export const onboardingHelpersStrings = dict(FA, EN)
