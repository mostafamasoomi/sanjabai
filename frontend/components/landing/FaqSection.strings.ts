import { dict } from '@/lib/i18n'

const FA = {
  eyebrow: 'سوالات متداول',
  title: 'چیزهایی که معمولاً می‌پرسند',
}

const EN: typeof FA = {
  eyebrow: 'FAQ',
  title: 'Common questions',
}

export const faqSectionStrings = dict(FA, EN)
