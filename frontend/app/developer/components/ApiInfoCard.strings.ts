import { dict } from '@/lib/i18n'

const FA = {
  title: 'اطلاعات API',
  endpointLabel: 'Endpoint',
  endpointDesc: 'API سازگار با فرمت OpenAI — بدون تغییر در کد اصلی ادغام دهید.',
  rateLimitsTitle: 'محدودیت‌های نرخی بر اساس پلن',
  colPlan: 'پلن',
  colLimit: 'محدودیت درخواست',
}

const EN: typeof FA = {
  title: 'API info',
  endpointLabel: 'Endpoint',
  endpointDesc: 'OpenAI-compatible API format — integrate without changing your existing code.',
  rateLimitsTitle: 'Rate limits by plan',
  colPlan: 'Plan',
  colLimit: 'Request limit',
}

export const apiInfoCardStrings = dict(FA, EN)
