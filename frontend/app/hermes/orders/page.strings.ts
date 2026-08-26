import { dict } from '@/lib/i18n'

const FA = {
  loadError: 'خطا در دریافت سفارش‌ها',
  signIn: 'وارد شوید',
  loginToAccount: 'ورود به حساب',
  pageTitle: 'سفارش‌های سرور هرمس',
  newOrder: 'سفارش جدید',
  close: 'بستن',
  paymentSuccess: 'پرداخت با موفقیت انجام شد و سفارش شما ثبت شد. سفارش در صف تحویل قرار گرفت.',
  paymentFailed: 'پرداخت ناموفق بود یا لغو شد. مبلغی از حساب شما کسر نشده است.',
  paymentError: 'خطایی در پردازش پرداخت رخ داد. اگر مبلغی کسر شده باشد، به‌زودی بازمی‌گردد.',
  emptyTitle: 'هنوز سفارشی ثبت نکرده‌اید',
  emptyDescription: 'یک سرور هرمس سفارش دهید تا اینجا نمایش داده شود.',
  viewPlans: 'مشاهده پلن‌ها',
  orderNumber: (id: string) => `سفارش #${id}`,
  viewServer: 'مشاهده سرور',
  status: {
    pending_payment: 'در انتظار پرداخت',
    paid: 'پرداخت شد — در صف تحویل',
    provisioning: 'در حال راه‌اندازی',
    active: 'فعال',
    suspended: 'متوقف‌شده',
    cancelled: 'لغوشده',
    expired: 'منقضی‌شده',
  },
}

const EN: typeof FA = {
  loadError: 'Failed to load orders',
  signIn: 'Sign in',
  loginToAccount: 'Sign in to your account',
  pageTitle: 'Hermes server orders',
  newOrder: 'New order',
  close: 'Close',
  paymentSuccess: 'Payment succeeded and your order was placed. It is queued for delivery.',
  paymentFailed: 'Payment failed or was cancelled. No amount was deducted from your account.',
  paymentError: 'An error occurred while processing payment. If an amount was deducted, it will be refunded shortly.',
  emptyTitle: "You haven't placed an order yet",
  emptyDescription: 'Order a Hermes server to see it here.',
  viewPlans: 'View plans',
  orderNumber: (id) => `Order #${id}`,
  viewServer: 'View server',
  status: {
    pending_payment: 'Pending payment',
    paid: 'Paid — queued for delivery',
    provisioning: 'Provisioning',
    active: 'Active',
    suspended: 'Suspended',
    cancelled: 'Cancelled',
    expired: 'Expired',
  },
}

export const hermesOrdersStrings = dict(FA, EN)
