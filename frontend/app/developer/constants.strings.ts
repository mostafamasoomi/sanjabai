import { dict } from '@/lib/i18n'

/* Backs constants.ts: the plan names / rate-limit descriptions and endpoint
   descriptions are prose and get translated here. The code samples
   (CODE_EXAMPLES) and the method/path/body fields of ENDPOINTS stay as they
   are -- they are code, not prose (see the i18n handoff spec on code
   samples). */

const FA = {
  forbiddenMessage: 'درخواست شما رد شد (خطای امنیتی). لطفاً صفحه را تازه‌سازی کرده و دوباره تلاش کنید.',
  rateLimits: [
    { plan: 'رایگان / بدون اشتراک', requests: '۳۰ درخواست در دقیقه' },
    { plan: 'پایه (pro)', requests: '۱۲۰ درخواست در دقیقه' },
    { plan: 'سازمانی (enterprise)', requests: '۳۰۰ درخواست در دقیقه' },
  ],
  endpointDescs: {
    '/v1/chat/completions': 'ارسال درخواست چت — سازگار با OpenAI',
    '/v1/models': 'دریافت لیست مدل‌های موجود',
  } as Record<string, string>,
}

const EN: typeof FA = {
  forbiddenMessage: 'Your request was rejected (security error). Please refresh the page and try again.',
  rateLimits: [
    { plan: 'Free / no subscription', requests: '30 requests/minute' },
    { plan: 'Pro', requests: '120 requests/minute' },
    { plan: 'Enterprise', requests: '300 requests/minute' },
  ],
  endpointDescs: {
    '/v1/chat/completions': 'Send a chat request — OpenAI-compatible',
    '/v1/models': 'List the available models',
  },
}

export const developerConstantsStrings = dict(FA, EN)
