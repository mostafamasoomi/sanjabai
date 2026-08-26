'use client'

import { Icon } from '@/components/ui/Icon'
import type { Lang } from '@/components/LanguageToggle'

/* ═══════════════════════════════════════════════════════════════
   Shared types, constants, and helpers for the skills marketplace
   (list page + detail page). Previously duplicated verbatim in both
   app/skills/page.tsx and app/skills/[id]/page.tsx.
   ═══════════════════════════════════════════════════════════════ */

export type SkillVariable = {
  name: string
  description: string
  type?: string
  default?: string
}

export type Skill = {
  id: number
  title: string
  title_fa: string
  description: string
  description_fa: string
  category: string
  prompt_template: string
  variables: SkillVariable[]
  default_model: string
  is_public: boolean
  is_featured: boolean
  usage_count: number
  rating_sum: number
  rating_count: number
  tags: string[]
  user_id: number
  created_at: string
}

export type UseResult = {
  rendered_prompt: string
  model: string
}

export const CATEGORY_KEYS = ['all', 'writing', 'coding', 'analysis', 'translation', 'marketing', 'other'] as const

export type CategoryKey = (typeof CATEGORY_KEYS)[number]

const CATEGORY_LABEL_FA: Record<CategoryKey, string> = {
  all: 'همه',
  writing: 'نوشتن',
  coding: 'برنامه‌نویسی',
  analysis: 'تحلیل',
  translation: 'ترجمه',
  marketing: 'بازاریابی',
  other: 'سایر',
}

const CATEGORY_LABEL_EN: Record<CategoryKey, string> = {
  all: 'All',
  writing: 'Writing',
  coding: 'Coding',
  analysis: 'Analysis',
  translation: 'Translation',
  marketing: 'Marketing',
  other: 'Other',
}

/** Label for a skill category, in the given language. `raw` may be a value
 *  the DB has that this table doesn't (a category added after this list),
 *  in which case it renders as itself rather than as `undefined` — same
 *  fallback shape as admin's `availabilityLabel`. */
export function categoryLabel(raw: string, lang: Lang = 'fa'): string {
  const table = lang === 'en' ? CATEGORY_LABEL_EN : CATEGORY_LABEL_FA
  return table[raw as CategoryKey] || raw
}

export const CATEGORY_BADGES: Record<string, string> = {
  writing: 'aurora-cap-blue',
  coding: 'aurora-cap-purple',
  analysis: 'aurora-cap-amber',
  translation: 'aurora-cap-cyan',
  marketing: 'aurora-cap-green',
  other: 'aurora-cap-default',
}

export function renderStars(rating: number, size = 14) {
  const stars = []
  for (let i = 1; i <= 5; i++) {
    stars.push(
      <Icon
        key={i}
        name="sparkles"
        size={size}
        className={i <= Math.round(rating) ? 'text-[var(--warning)]' : 'text-[var(--text-muted)]'}
        style={{ opacity: i <= Math.round(rating) ? 1 : 0.3 }}
      />
    )
  }
  return stars
}

export function getAverageRating(s: Skill): number {
  return s.rating_count > 0 ? s.rating_sum / s.rating_count : 0
}
