import { type IconName } from '@/components/ui/Icon'

/* ═══ Template gallery — data model ═══════════════════════════════════════
   14 starter "recipes" shown on /guide, each showcasing a high-productivity
   COMBINATION of features rather than a single feature in isolation (the
   tour teaches combos the same way — see ProductTour.strings.ts's header).
   Two apply mechanics, both zero backend work:
     - 'chat-prefill': lands on /chat?prompt=<encoded>, which already reads
       ?prompt= and prefills + focuses the composer (app/chat/page.tsx).
     - 'navigate': a plain link to an existing page (e.g. /assistants/new)
       where the user builds the recipe themselves; nothing to prefill there.
   Copy (title/tagline/ingredients/applyLabel/prompt) lives in
   templates.strings.fa.ts / .en.ts, bilingual like every other `.strings.ts`
   pair in this codebase. This file only holds the shape, the fixed display
   order, and the one function that turns an `apply` into an href — kept
   here so the URL-encoding happens ONCE, at render time, never baked into
   copy (a raw '%20' etc. in a prompt string would violate the no-digit
   product-contract rule the tests enforce on copy fields; encoding here
   means the SOURCE prompt strings stay plain, only the rendered href is
   encoded). */

export type TemplateId =
  | 'fa-editor'
  | 'code-advisor'
  | 'tone-translator'
  | 'contract-analyzer'
  | 'report-summarizer'
  | 'meeting-decisions'
  | 'daily-summary'
  | 'weekly-review'
  | 'customer-followup'
  | 'combo-backup'
  | 'smart-mode-everyday'
  | 'compare-first'
  | 'formal-email'
  | 'idea-to-post'

export type TemplateTheme = 'expert' | 'document' | 'automation' | 'reliability' | 'everyday'

export type TemplateApply =
  | { kind: 'chat-prefill'; prompt: string; smartHint?: boolean }
  | { kind: 'navigate'; href: string }

export type TourTemplate = {
  id: TemplateId
  theme: TemplateTheme
  icon: IconName
  /** The feature combination this recipe showcases, e.g. "دستیار + مهارت + حافظه". */
  combo: string
  title: string
  tagline: string
  /** >=2 concrete steps to build/use the recipe. */
  ingredients: string[]
  apply: TemplateApply
  applyLabel: string
}

/** Fixed display order, grouped by theme (expert, document, automation,
 *  reliability, everyday) — matches the keys of templates.strings.fa/en.ts. */
export const TEMPLATE_ORDER: readonly TemplateId[] = [
  'fa-editor',
  'code-advisor',
  'tone-translator',
  'contract-analyzer',
  'report-summarizer',
  'meeting-decisions',
  'daily-summary',
  'weekly-review',
  'customer-followup',
  'combo-backup',
  'smart-mode-everyday',
  'compare-first',
  'formal-email',
  'idea-to-post',
]

/** Builds the real href for a template's apply button. `chat-prefill` always
 *  resolves to `/chat?prompt=` — /chat has no `?smart=` param to read (only
 *  `?prompt=`, `?assistant=`, `?model=`), so `smartHint` is a copy signal
 *  only (the ingredient list tells the user to flip smart mode on) and never
 *  changes the URL. Encoding happens here, never in the stored prompt. */
export function templateApplyHref(t: TourTemplate): string {
  if (t.apply.kind === 'navigate') return t.apply.href
  return '/chat?prompt=' + encodeURIComponent(t.apply.prompt)
}
