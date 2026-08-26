import { dict } from '@/lib/i18n'

const FA = {
  toLight: 'تغییر به حالت روشن',
  toDark: 'تغییر به حالت تاریک',
}

const EN: typeof FA = {
  toLight: 'Switch to light mode',
  toDark: 'Switch to dark mode',
}

export const themeToggleStrings = dict(FA, EN)
