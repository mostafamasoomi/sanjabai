import { dict } from '@/lib/i18n'

const FA = {
  title: 'پلتفرم توسعه‌دهندگان',
  subtitle: 'API سازگار با OpenAI برای ادغام در اپلیکیشن‌های شما',
}

const EN: typeof FA = {
  title: 'Developer platform',
  subtitle: 'An OpenAI-compatible API to integrate into your applications',
}

export const developerPageStrings = dict(FA, EN)
