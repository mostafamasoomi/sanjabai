/* Shared primitives referenced by several content sections below — kept
   separate so every section that needs them (stats, steps, pricing, faq,
   api) can import without pulling in the rest of the landing copy.

   These two are plain per-language constants rather than a dict() reader:
   they are text fragments interpolated into OTHER content modules' FA/EN
   objects at module-eval time (e.g. `` `حداقل شارژ ${MIN_TOPUP_LABEL_FA}` ``),
   so both language variants must exist simultaneously — a `(lang) => value`
   reader can't do that without picking a lang before the caller has one. */

/** Documented in app/developer/page.tsx. The bare domain; there is no `api.` subdomain.
 *  A URL, not UI copy — identical in both languages. */
export const API_BASE_URL = 'https://sanjabai.com/v1'

/** app/wallet/page.tsx → MIN_TOPUP (10_000 raw toman). Both strings name the
 *  exact same amount; only the wording/numerals differ per language. */
export const MIN_TOPUP_LABEL_FA = '۱۰ هزار تومان'
export const MIN_TOPUP_LABEL_EN = '10,000 Toman'
