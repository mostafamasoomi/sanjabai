import { dict } from '@/lib/i18n'

const FA = {
  hint: 'به نظر می‌رسد می‌خواهید در اینترنت جستجو شود، ولی جستجوی وب خاموش است.',
  enableAndResend: 'فعال‌سازی جستجوی وب و ارسال دوباره',
  close: 'بستن',
}

const EN: typeof FA = {
  hint: 'It looks like you want to search the web, but web search is off.',
  enableAndResend: 'Enable web search and resend',
  close: 'Close',
}

export const searchHintBannerStrings = dict(FA, EN)
