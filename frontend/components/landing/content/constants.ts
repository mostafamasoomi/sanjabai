/* Shared primitives referenced by several content sections below — kept
   separate so every section that needs them (stats, steps, pricing, faq,
   api) can import without pulling in the rest of the landing copy. */

/** Documented in app/developer/page.tsx. The bare domain; there is no `api.` subdomain. */
export const API_BASE_URL = 'https://sanjabai.com/v1'

/** app/wallet/page.tsx → MIN_TOPUP */
export const MIN_TOPUP_LABEL = '۱۰ هزار تومان'
