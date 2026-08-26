import { dict } from '@/lib/i18n'

const FA = {
  title: 'اعلان‌ها',
  email: 'اعلان ایمیلی',
  emailHint: 'دریافت اعلان‌ها از طریق ایمیل',
  telegram: 'اعلان تلگرامی',
  telegramHint: 'دریافت اعلان‌ها از طریق ربات تلگرام',
}

const EN: typeof FA = {
  title: 'Notifications',
  email: 'Email Notifications',
  emailHint: 'Receive notifications via email',
  telegram: 'Telegram Notifications',
  telegramHint: 'Receive notifications via Telegram bot',
}

export const notificationsSectionStrings = dict(FA, EN)
