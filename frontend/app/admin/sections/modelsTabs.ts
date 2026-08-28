/* Sub-tab table for the models & pricing module.
 *
 * Split out of ModelsModule.tsx on purpose: AdminPanel needs `tabFromSearch`
 * on mount, to seed its state from `?tab=` before anything is rendered. If it
 * imported that from ModelsModule directly, the static import would pull
 * ModelsModule into the shell's own chunk and its `dynamic(..., {ssr:false})`
 * would only be deferring the render, not the download. This file has no
 * component imports, so both sides can take it eagerly for free.
 */

export type ModelsTab =
  | 'catalog' | 'logical' | 'overhead' | 'router-probe' | 'default'
  | 'pricing' | 'image-pricing' | 'exchange-rate' | 'markup'

/* Two groups, rendered with a divider between them: what a model IS, then
 * what it COSTS. The order inside each group is the order the work happens
 * in -- discover a model, map it, measure it, then price it.
 *
 * `label` is the Persian string and `labelEn` its sibling; ModelsModule.tsx
 * renders whichever the active language calls for via the `t()` helper in
 * ../adminLabels. */
export const MODELS_TABS: { key: ModelsTab; label: string; labelEn: string; group: 'catalog' | 'pricing' }[] = [
  { key: 'catalog', label: 'کاتالوگ و عملیات', labelEn: 'Catalog & Operations', group: 'catalog' },
  { key: 'logical', label: 'مدل‌های منطقی', labelEn: 'Logical Models', group: 'catalog' },
  { key: 'overhead', label: 'توکن تزریقی بالادست', labelEn: 'Upstream Token Overhead', group: 'catalog' },
  { key: 'router-probe', label: 'پروب روتر هوشمند', labelEn: 'Smart Router Probe', group: 'catalog' },
  { key: 'default', label: 'مدل پیش‌فرض', labelEn: 'Default Model', group: 'catalog' },
  { key: 'pricing', label: 'تعرفه‌ها', labelEn: 'Tariffs', group: 'pricing' },
  { key: 'image-pricing', label: 'قیمت‌گذاری تصویر', labelEn: 'Image Pricing', group: 'pricing' },
  { key: 'exchange-rate', label: 'نرخ ارز', labelEn: 'Exchange Rate', group: 'pricing' },
  { key: 'markup', label: 'درصد سود', labelEn: 'Markup', group: 'pricing' },
]

export const DEFAULT_MODELS_TAB: ModelsTab = 'catalog'

const TAB_KEYS = new Set<string>(MODELS_TABS.map((t) => t.key))

export function isModelsTab(raw: string): raw is ModelsTab {
  return TAB_KEYS.has(raw)
}

/** The sub-tab named by `?tab=`, or the default when it names nothing valid.
 *  A URL carrying a retired or misspelled tab must land somewhere real
 *  rather than render an empty module body. */
export function tabFromSearch(search: string): ModelsTab {
  const raw = new URLSearchParams(search).get('tab') || ''
  return isModelsTab(raw) ? raw : DEFAULT_MODELS_TAB
}
