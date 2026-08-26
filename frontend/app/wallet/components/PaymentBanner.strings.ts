import { dict } from '@/lib/i18n'

const FA = {
  close: 'بستن',
  success: 'پرداخت با موفقیت انجام شد و کیف پول شما شارژ شد.',
  failed: 'پرداخت ناموفق بود یا لغو شد. مبلغی از حساب شما کسر نشده است.',
  error: 'خطایی در پردازش پرداخت رخ داد. اگر مبلغی کسر شده باشد، به‌زودی بازمی‌گردد.',
}

const EN: typeof FA = {
  close: 'Close',
  success: 'Payment succeeded and your wallet has been topped up.',
  failed: 'Payment failed or was cancelled. Nothing was deducted from your account.',
  error: 'An error occurred while processing the payment. If anything was deducted, it will be refunded shortly.',
}

export const paymentBannerStrings = dict(FA, EN)
