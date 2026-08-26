import type { Lang } from '@/components/LanguageToggle'
import { memoryCategoryStrings } from './memoryTypes.strings'

/* ═══════════════════════════════════════════════════════════════
   Types
   Split out of page.tsx verbatim -- no behaviour change.

   CATEGORIES/CATEGORY_MAP became functions of `lang`: this file is not a
   component, so it takes `lang` as an explicit parameter rather than
   calling `useLang()` (see the i18n spec).
   ═══════════════════════════════════════════════════════════════ */

export type Memory = {
  id: number
  content: string
  category: string
  source: string
  tags: string[]
  created_at: string
  updated_at: string
}

export type Category = { key: string; label: string }

export function categories(lang: Lang): Category[] {
  const l = memoryCategoryStrings(lang)
  return [
    { key: '', label: l.all },
    { key: 'preferences', label: l.preferences },
    { key: 'projects', label: l.projects },
    { key: 'skills', label: l.skills },
    { key: 'personal', label: l.personal },
    { key: 'other', label: l.other },
  ]
}

export function categoryMap(lang: Lang): Record<string, string> {
  const l = memoryCategoryStrings(lang)
  return {
    '': l.all,
    preferences: l.preferences,
    projects: l.projects,
    skills: l.skills,
    personal: l.personal,
    other: l.other,
  }
}
