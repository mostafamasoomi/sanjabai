import { dict } from '@/lib/i18n'

/* Strings for memoryTypes.ts's CATEGORIES/CATEGORY_MAP. memoryTypes.ts is not
 * a component, so these are read with an explicit `lang` argument -- see the
 * i18n spec ("a non-component helper takes lang as a parameter instead"). */

const FA = {
  all: 'همه',
  preferences: 'ترجیحات',
  projects: 'پروژه‌ها',
  skills: 'مهارت‌ها',
  personal: 'شخصی',
  other: 'سایر',
}

const EN: typeof FA = {
  all: 'All',
  preferences: 'Preferences',
  projects: 'Projects',
  skills: 'Skills',
  personal: 'Personal',
  other: 'Other',
}

export const memoryCategoryStrings = dict(FA, EN)
