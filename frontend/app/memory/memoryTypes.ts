/* ═══════════════════════════════════════════════════════════════
   Types
   Split out of page.tsx verbatim -- no behaviour change.
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

export const CATEGORIES: Category[] = [
  { key: '', label: 'همه' },
  { key: 'preferences', label: 'ترجیحات' },
  { key: 'projects', label: 'پروژه‌ها' },
  { key: 'skills', label: 'مهارت‌ها' },
  { key: 'personal', label: 'شخصی' },
  { key: 'other', label: 'سایر' },
]

export const CATEGORY_MAP: Record<string, string> = {
  '': 'همه',
  preferences: 'ترجیحات',
  projects: 'پروژه‌ها',
  skills: 'مهارت‌ها',
  personal: 'شخصی',
  other: 'سایر',
}
