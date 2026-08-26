import { dict } from '@/lib/i18n'

const FA = {
  balance: 'موجودی فعلی',
  topUp: 'شارژ کیف پول ←',
  spentThisMonth: 'مصرف این ماه',
  requestsCount: (n: string) => `${n} درخواست`,
  totalTokens: 'کل توکن‌های مصرفی',
  ioTokens: (input: string, output: string) => `ورودی: ${input} | خروجی: ${output}`,
  modelsUsed: 'مدل‌های استفاده شده',
  activeThisMonth: 'مدل فعال این ماه',
}

const EN: typeof FA = {
  balance: 'Current balance',
  topUp: 'Top up wallet →',
  spentThisMonth: 'Spent this month',
  requestsCount: (n) => `${n} requests`,
  totalTokens: 'Total tokens used',
  ioTokens: (input, output) => `In: ${input} | Out: ${output}`,
  modelsUsed: 'Models used',
  activeThisMonth: 'Active models this month',
}

export const summaryCardsStrings = dict(FA, EN)
