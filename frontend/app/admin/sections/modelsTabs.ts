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
  | 'catalog' | 'logical' | 'overhead' | 'default'
  | 'pricing' | 'image-pricing' | 'exchange-rate' | 'markup'

/* Two groups, rendered with a divider between them: what a model IS, then
 * what it COSTS. The order inside each group is the order the work happens
 * in -- discover a model, map it, measure it, then price it. */
export const MODELS_TABS: { key: ModelsTab; label: string; group: 'catalog' | 'pricing' }[] = [
  { key: 'catalog', label: 'کاتالوگ و عملیات', group: 'catalog' },
  { key: 'logical', label: 'مدل‌های منطقی', group: 'catalog' },
  { key: 'overhead', label: 'توکن تزریقی بالادست', group: 'catalog' },
  { key: 'default', label: 'مدل پیش‌فرض', group: 'catalog' },
  { key: 'pricing', label: 'تعرفه‌ها', group: 'pricing' },
  { key: 'image-pricing', label: 'قیمت‌گذاری تصویر', group: 'pricing' },
  { key: 'exchange-rate', label: 'نرخ ارز', group: 'pricing' },
  { key: 'markup', label: 'درصد سود', group: 'pricing' },
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
