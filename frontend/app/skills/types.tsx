'use client'

import { Icon } from '@/components/ui/Icon'

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

export const CATEGORIES = [
  { key: 'all', label: 'همه' },
  { key: 'writing', label: 'نوشتن' },
  { key: 'coding', label: 'برنامه‌نویسی' },
  { key: 'analysis', label: 'تحلیل' },
  { key: 'translation', label: 'ترجمه' },
  { key: 'marketing', label: 'بازاریابی' },
  { key: 'other', label: 'سایر' },
]

export const CATEGORY_BADGES: Record<string, string> = {
  writing: 'aurora-cap-blue',
  coding: 'aurora-cap-purple',
  analysis: 'aurora-cap-amber',
  translation: 'aurora-cap-cyan',
  marketing: 'aurora-cap-green',
  other: 'aurora-cap-default',
}

export const CATEGORY_LABELS: Record<string, string> = {
  writing: 'نوشتن',
  coding: 'برنامه‌نویسی',
  analysis: 'تحلیل',
  translation: 'ترجمه',
  marketing: 'بازاریابی',
  other: 'سایر',
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
