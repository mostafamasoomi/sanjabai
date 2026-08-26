import { dict } from '@/lib/i18n'

const FA = {
  subscriptionActive: 'اشتراک شما با موفقیت فعال شد.',
  paymentSuccess: 'پرداخت با موفقیت انجام شد.',
  paymentFailed: 'پرداخت ناموفق بود یا لغو شد. مبلغی از حساب شما کسر نشده است.',
  paymentError: 'خطایی در پردازش پرداخت رخ داد. اگر مبلغی کسر شده باشد، به‌زودی بازمی‌گردد.',
}

const EN: typeof FA = {
  subscriptionActive: 'Your subscription was activated successfully.',
  paymentSuccess: 'Payment completed successfully.',
  paymentFailed: 'Payment failed or was cancelled. No amount was deducted from your account.',
  paymentError: 'An error occurred while processing the payment. If any amount was deducted, it will be refunded soon.',
}

export const usePaymentBannerStrings = dict(FA, EN)
