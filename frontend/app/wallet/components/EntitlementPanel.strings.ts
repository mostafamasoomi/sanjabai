import { dict } from '@/lib/i18n'

const FA = {
  title: 'سهمیه بسته‌های شما',
  intro: 'این سهمیه‌ها جدا از موجودی تومانی کیف پول شما شمارش می‌شوند. با تمام یا منقضی شدن سهمیه یک بسته، هزینه درخواست‌های بعدی از موجودی کیف پول کسر خواهد شد.',
  expiresSoon: 'به‌زودی منقضی می‌شود',
  expires: 'انقضا',
  requestsRemaining: 'درخواست باقی‌مانده',
  requestUnit: 'درخواست',
  tokensRemaining: 'توکن باقی‌مانده',
  tokenUnit: 'توکن',
  unmetered: 'بدون محدودیت شمارشی',
  ceilingPrefix: 'سقف هزینه هر درخواست از این بسته:',
  ceilingSuffix: 'درخواست‌های گران‌تر از این سقف، از موجودی کیف پول شما کسر می‌شود، نه از این بسته.',
  noCeiling: 'برای این بسته سقف هزینه‌ای ثبت نشده؛ در نتیجه هزینه درخواست‌های شما از این سهمیه پوشش داده نمی‌شود و از موجودی کیف پول کسر می‌شود.',
}

const EN: typeof FA = {
  title: 'Your package quotas',
  intro: "These quotas are counted separately from your Toman wallet balance. Once a package's quota is used up or expires, further requests are billed from the wallet balance instead.",
  expiresSoon: 'Expiring soon',
  expires: 'Expires',
  requestsRemaining: 'Requests remaining',
  requestUnit: 'requests',
  tokensRemaining: 'Tokens remaining',
  tokenUnit: 'tokens',
  unmetered: 'No count-based limit',
  ceilingPrefix: 'Cost ceiling per request from this package:',
  ceilingSuffix: 'Requests above this ceiling are billed from your wallet balance, not from this package.',
  noCeiling: "This package has no cost ceiling set, so your requests aren't covered by this quota and are billed from your wallet balance instead.",
}

export const entitlementPanelStrings = dict(FA, EN)
