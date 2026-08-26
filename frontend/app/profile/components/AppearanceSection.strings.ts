import { dict } from '@/lib/i18n'

const FA = {
  title: 'ظاهر و زبان',
  darkMode: 'حالت تاریک',
  darkModeHint: 'استفاده از تم تاریک',
  languageLabel: 'زبان / Language',
  languageHint: 'فارسی یا انگلیسی',
}

const EN: typeof FA = {
  title: 'Appearance & Language',
  darkMode: 'Dark Mode',
  darkModeHint: 'Use dark theme',
  languageLabel: 'Language / زبان',
  languageHint: 'Persian or English',
}

export const appearanceSectionStrings = dict(FA, EN)
