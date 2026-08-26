import { dict } from '@/lib/i18n'

const FA = {
  truncatedEmpty: 'مدل بدون تولید متن به محدودیت طول رسید.',
  retry: 'تلاش دوباره',
  truncated: 'این پاسخ به‌خاطر محدودیت طول ناتمام ماند.',
  continue: 'ادامه بده',
  copy: 'کپی',
  copied: 'کپی شد',
  retryAgain: 'تلاش مجدد',
}

const EN: typeof FA = {
  truncatedEmpty: 'The model hit the length limit without producing any text.',
  retry: 'Try again',
  truncated: 'This response was cut off by the length limit.',
  continue: 'Continue',
  copy: 'Copy',
  copied: 'Copied',
  retryAgain: 'Retry',
}

export const chatMessageItemStrings = dict(FA, EN)
