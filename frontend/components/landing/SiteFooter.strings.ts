import { dict } from '@/lib/i18n'

const FA = {
  tagline: 'پلتفرم فارسی دسترسی به مدل‌های هوش مصنوعی. چت کنید، عامل بسازید و با یک API به محصولتان وصل شوید — با پرداخت ریالی و پشتیبانی محلی.',
  // Takes the year rather than baking one in. It was «۱۴۰۴» here and «2025»
  // in English -- both already a year out of date, and a hardcoded year goes
  // stale again every New Year. The two calendars also disagree, so each side
  // formats its own.
  copyright: (year: string) => `© ${year} Sanjabai — تمامی حقوق محفوظ است.`,
  madeFor: 'ساخته‌شده برای کاربران فارسی‌زبان',
}

const EN: typeof FA = {
  tagline: 'A Persian-first platform for AI models. Chat, build agents, and connect to your product with one API — with local card payment and local support.',
  copyright: (year) => `© ${year} Sanjabai — All rights reserved.`,
  madeFor: 'Built for Persian-speaking users',
}

export const siteFooterStrings = dict(FA, EN)
