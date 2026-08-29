// Tour v2 anchor registry — the single source of truth for every element the
// interactive product tour can spotlight. Anchors are ALWAYS applied through
// `tourAnchor(id)` with a string literal (never a raw data-tour= attribute) so
// the wiring-guard test can assert each anchor exists exactly once by grepping
// for `tourAnchor('<id>')`. A duplicate would spotlight the wrong element (the
// skills/combos empty-state twins are the live hazard), so uniqueness matters.

export type TourAnchorId =
  | 'topbar.help'
  | 'chat.composer'
  | 'chat.attach'
  | 'chat.smartMode'
  | 'assistants.create'
  | 'skills.create'
  | 'memory.header'
  | 'combos.create'
  | 'tasks.create'
  | 'models.search'
  | 'compare.prompt'
  | 'guide.templates'

export const TOUR_ANCHOR_ATTR = 'data-tour'

/** Spread onto the target element: `<button {...tourAnchor('assistants.create')}>`. */
export function tourAnchor(id: TourAnchorId) {
  return { [TOUR_ANCHOR_ATTR]: id } as const
}

/** Locate a tagged element in the live DOM, or null if it is not currently mounted. */
export function findAnchor(id: TourAnchorId): HTMLElement | null {
  if (typeof document === 'undefined') return null
  return document.querySelector<HTMLElement>(`[${TOUR_ANCHOR_ATTR}="${id}"]`)
}
