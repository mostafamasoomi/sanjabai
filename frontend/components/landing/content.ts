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
   ═══════════════════════════════════════════════════════════════════════════ */

export { API_BASE_URL, MIN_TOPUP_LABEL } from './content/constants'
export { NAV_LINKS } from './content/nav'
export { HERO_ROTATION, HERO_TRUST, PREVIEW_THREADS } from './content/hero'
export type { PreviewThread } from './content/hero'
export { CATALOG } from './content/catalog'
export { STATS } from './content/stats'
export { FEATURES } from './content/features'
export type { Feature } from './content/features'
export { CAPABILITY_TABS, MEMORY_SAMPLES, DOCUMENT_TYPES, TASK_SAMPLES } from './content/capabilities'
export type { CapabilityTab } from './content/capabilities'
export { COMPARISON_ROWS } from './content/comparison'
export type { ComparisonRow } from './content/comparison'
export { STEPS } from './content/steps'
export { API_POINTS, CODE_SAMPLES } from './content/api'
export { PRICING_COLUMNS } from './content/pricing'
export type { PricingColumn } from './content/pricing'
export { FAQ } from './content/faq'
export { FOOTER_COLUMNS } from './content/footer'
