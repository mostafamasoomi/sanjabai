import { dict } from '@/lib/i18n'

const FA = {
  eyebrow: 'فراتر از چت',
  title: 'دستیاری که یادش می‌ماند، برایتان می‌سازد و به‌موقع کارش را انجام می‌دهد',
  lead: 'همه در همان فضای کاری — بدون افزونه‌ی جدا و بدون نرم‌افزار اضافه.',
  tabsAria: 'قابلیت‌ها',
}

const EN: typeof FA = {
  eyebrow: 'Beyond chat',
  title: 'An assistant that remembers, builds for you, and shows up on time',
  lead: 'All in the same workspace — no separate plugin, no extra software.',
  tabsAria: 'Capabilities',
}

export const capabilityShowcaseStrings = dict(FA, EN)
