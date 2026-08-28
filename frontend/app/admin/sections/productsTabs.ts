/* Sub-tab table for the products module (mirrors modelsTabs.ts).
 *
 * Split out of ProductsModule.tsx on purpose: AdminPanel needs
 * `tabFromSearch` on mount, to seed its state from `?tab=` before anything
 * is rendered. If it imported that from ProductsModule directly, the static
 * import would pull ProductsModule into the shell's own chunk and its
 * `dynamic(..., {ssr:false})` would only be deferring the render, not the
 * download. This file has no component imports, so both sides can take it
 * eagerly for free.
 */

export type ProductsTab = 'packages' | 'limits' | 'purchases' | 'referral'

/* Four sub-tabs, in the order the work happens in: edit what a package
 * sells and costs, then its rate-limit threshold, then what buyers actually
 * paid for it, then the separate referral-reward settings (F-REF phase 5 --
 * unrelated to credit_packages, but there is no other nav slot for it and
 * AdminPanel.tsx is senior-owned, so it rides here as a fourth sub-tab
 * rather than a new sidebar entry).
 *
 * `label` is the Persian string and `labelEn` its sibling; ProductsModule.tsx
 * renders whichever the active language calls for via the `t()` helper in
 * ../adminLabels. */
export const PRODUCTS_TABS: { key: ProductsTab; label: string; labelEn: string }[] = [
  { key: 'packages', label: 'بسته‌ها', labelEn: 'Packages' },
  { key: 'limits', label: 'سقف مصرف', labelEn: 'Limits' },
  { key: 'purchases', label: 'خریدها', labelEn: 'Purchases' },
  { key: 'referral', label: 'دعوت دوستان', labelEn: 'Referrals' },
]

export const DEFAULT_PRODUCTS_TAB: ProductsTab = 'packages'

const TAB_KEYS = new Set<string>(PRODUCTS_TABS.map((t) => t.key))

export function isProductsTab(raw: string): raw is ProductsTab {
  return TAB_KEYS.has(raw)
}

/** The sub-tab named by `?tab=`, or the default when it names nothing valid.
 *  A URL carrying a retired or misspelled tab must land somewhere real
 *  rather than render an empty module body. */
export function tabFromSearch(search: string): ProductsTab {
  const raw = new URLSearchParams(search).get('tab') || ''
  return isProductsTab(raw) ? raw : DEFAULT_PRODUCTS_TAB
}
