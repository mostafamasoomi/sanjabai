import { dict } from '@/lib/i18n'

const FA = {
  title: 'اتصال تلگرام',
  intro: 'با اتصال حساب تلگرام می‌توانید از طریق ربات Sanjabai چت کنید و موجودی خود را ببینید.',
  idPlaceholder: 'شناسه عددی تلگرام (Telegram ID)',
  link: 'اتصال',
  hint: 'برای دریافت شناسه تلگرام، به ربات @userinfobot پیام دهید.',
}

const EN: typeof FA = {
  title: 'Link Telegram',
  intro: 'Link your Telegram account to chat via the Sanjabai bot and view your balance.',
  idPlaceholder: 'Telegram numeric ID',
  link: 'Link',
  hint: 'To get your Telegram ID, message @userinfobot.',
}

export const telegramLinkSectionStrings = dict(FA, EN)
