import type { IconName } from '@/components/ui/Icon'

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
  { key: 'coding', label: 'برنامهنویسی' },
  { key: 'analysis', label: 'تحلیل' },
  { key: 'translation', label: 'ترجمه' },
  { key: 'marketing', label: 'بازاریابی' },
  { key: 'other', label: 'سایر' },
]

export const SORT_OPTIONS = [
  { key: 'popular', label: 'محبوبترین' },
  { key: 'newest', label: 'جدیدترین' },
  { key: 'top_rated', label: 'بهترین امتیاز' },
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
  coding: 'برنامهنویسی',
  analysis: 'تحلیل',
  translation: 'ترجمه',
  marketing: 'بازاریابی',
  other: 'سایر',
}

export function faNumber(n: number): string {
  return n.toLocaleString('fa-IR')
}

export function getAverageRating(s: Skill): number {
  return s.rating_count > 0 ? s.rating_sum / s.rating_count : 0
}