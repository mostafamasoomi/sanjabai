import { dict } from '@/lib/i18n'

const FA = {
  usageCount: (n: string) => `${n} استفاده`,
  useAction: 'استفاده',
}

const EN: typeof FA = {
  usageCount: (n) => `${n} uses`,
  useAction: 'Use',
}

export const skillCardStrings = dict(FA, EN)
