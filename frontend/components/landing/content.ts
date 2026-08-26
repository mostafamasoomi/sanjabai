/* ═══════════════════════════════════════════════════════════════════════════
   Landing copy + data.

   All marketing text lives here rather than being inlined in JSX. One file to
   proofread, one file to hand to a translator, and the section components stay
   readable as layout.

   ───────────────────────────────────────────────────────────────────────────
   Every factual claim below is sourced from the codebase, not invented:

   - Model list        backend/litellm_config.yaml  (23 chat models)
   - API base URL      app/developer/page.tsx       (https://sanjabai.com/v1)
   - Billing model     app/pricing/page.tsx         (per-token, wallet, no
                                                     monthly subscription)
   - Top-up amounts    app/wallet/page.tsx          (PRESET_AMOUNTS, MIN_TOPUP)

   If you add a claim here, make sure something in the repo backs it up.

   This file is a barrel: the actual copy/data lives in ./content/*, split by
   landing-page section so no single file grows unwieldy. Every symbol below
   is re-exported unchanged so existing imports of `@/components/landing/content`
   keep working exactly as before.

   Bilingual note: the section modules under ./content/* now export a
   `(lang) => data` reader (see lib/i18n.ts `dict`) instead of a flat
   Persian-only constant, so a section can render in English once the
   language toggle is flipped. `FAQ` is the one exception, kept as a flat
   Persian array for app/page.tsx's JSON-LD FAQ schema, which is a Server
   Component outside components/landing and isn't language-toggle-aware.
   ═══════════════════════════════════════════════════════════════════════════ */

export { API_BASE_URL, MIN_TOPUP_LABEL_FA, MIN_TOPUP_LABEL_EN } from './content/constants'
export { navContent } from './content/nav'
export { heroContent } from './content/hero'
export type { PreviewThread } from './content/hero'
export { CATALOG } from './content/catalog'
export { statsContent } from './content/stats'
export { featuresContent } from './content/features'
export type { Feature } from './content/features'
export { capabilitiesContent } from './content/capabilities'
export type { CapabilityTab } from './content/capabilities'
export { comparisonContent } from './content/comparison'
export type { ComparisonRow } from './content/comparison'
export { stepsContent } from './content/steps'
export { apiContent } from './content/api'
export { pricingContent } from './content/pricing'
export type { PricingColumn } from './content/pricing'
export { FAQ, faqContent } from './content/faq'
export { footerContent } from './content/footer'
