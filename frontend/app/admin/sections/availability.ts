/* The one place `model_catalog.availability` is turned into Persian.
 *
 * Four sub-tabs of the models & pricing module render this same column, and
 * before this file each kept its own literal map with a comment promising it
 * was hand-synced with the others. They were not. Measured across the four
 * copies at the time this was written:
 *
 *   key           tariffs      catalog       logical         image
 *   available     «فعال»       «در دسترس»    «در دسترس»      «در دسترس»
 *   degraded      کاهش‌یافته    کاهش‌یافته     کاهش‌یافته       کاهش‌یافته
 *   maintenance   «تعمیرات»    «در تعمیر»    «در حال تعمیر»  «در حال تعمیر»
 *   disabled      غیرفعال      غیرفعال       غیرفعال         غیرفعال
 *
 * So one model read as three different states depending on which tab the
 * admin happened to have open. Hand-syncing four literals is not a strategy;
 * one import is.
 *
 * The values mirror the backend's `_VALID_AVAILABILITY` enum
 * (backend/admin_catalog.py) and the DB CHECK constraint on
 * model_catalog.availability. `logical_model.availability` is a *different*
 * column with an identical enum (migrations/0025_logical_models.sql), and
 * deliberately shares these labels: they name the same four states, and a
 * logical model reading differently from the catalog row it points at is the
 * confusion this file exists to remove.
 */

import type { Lang } from '@/components/LanguageToggle'

export const AVAILABILITY_OPTIONS = ['available', 'degraded', 'maintenance', 'disabled'] as const

export type Availability = (typeof AVAILABILITY_OPTIONS)[number]

/** Persian label. Won the vote 3-to-1 for `available`, and «در حال تعمیر»
 *  over «در تعمیر»/«تعمیرات» for being the least ambiguous of the three. */
export const AVAILABILITY_FA: Record<string, string> = {
  available: 'در دسترس',
  degraded: 'کاهش‌یافته',
  maintenance: 'در حال تعمیر',
  disabled: 'غیرفعال',
}

/** Badge class, for tables that render the state as a pill. */
export const AVAILABILITY_BADGE: Record<string, string> = {
  available: 'badge-positive',
  degraded: 'badge-warning',
  maintenance: 'badge-accent',
  disabled: 'badge-danger',
}

/** Raw colour, for the places that draw a dot or a border rather than a pill. */
export const AVAILABILITY_COLOR: Record<string, string> = {
  available: 'var(--success, #22c55e)',
  degraded: 'var(--warning, #f59e0b)',
  maintenance: 'var(--muted, #8b8b8b)',
  disabled: 'var(--danger, #ef4444)',
}

/** The only two states `POST /admin/models/{id}/toggle` can move between --
 *  it 400s on anything else (admin_pricing.py). Rendering a clickable toggle
 *  on a `degraded`/`maintenance` row is a button that always fails, and
 *  1,155 of the ~1,200 catalog rows are `maintenance`. */
export const TOGGLEABLE = new Set<string>(['available', 'disabled'])

/** English label. Same four states, same one-import rule — the reason this
 *  file exists is that four hand-synced copies of a label map were not in
 *  fact in sync, and adding a second language multiplies that failure. */
export const AVAILABILITY_EN: Record<string, string> = {
  available: 'Available',
  degraded: 'Degraded',
  maintenance: 'Maintenance',
  disabled: 'Disabled',
}

/** Label for an unknown value, so a state added to the DB before this file
 *  knows about it renders as itself rather than as `undefined`.
 *
 *  `lang` is optional and defaults to Persian so the call sites that have not
 *  been translated yet keep their current behaviour. */
export function availabilityLabel(raw: string, lang: Lang = 'fa'): string {
  const table = lang === 'en' ? AVAILABILITY_EN : AVAILABILITY_FA
  return table[raw] || raw
}
