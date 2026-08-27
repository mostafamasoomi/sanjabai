import { dict } from '@/lib/i18n'

const FA = {
  title: 'خریدها',
  subtitle: (n: string) => `${n} خرید تکمیل‌شده`,
  colUser: 'کاربر',
  colPackage: 'بسته',
  colAmount: 'مبلغ پرداختی',
  colCredits: 'اعتبار واریزی',
  colStatus: 'وضعیت',
  colVerifiedAt: 'تأیید پرداخت',
  colCreatedAt: 'تاریخ',
  loading: 'در حال بارگذاری...',
  loadError: 'خطا در بارگذاری خریدها',
  retry: 'تلاش دوباره',
  noPurchases: 'هیچ خریدی ثبت نشده است',
  page: (p: string, total: string, count: string) => `صفحه ${p} از ${total} — ${count} خرید`,
  prev: 'قبلی',
  next: 'بعدی',
}

const EN: typeof FA = {
  title: 'Purchases',
  subtitle: (n) => `${n} completed purchase${n === '۱' || n === '1' ? '' : 's'}`,
  colUser: 'User',
  colPackage: 'Package',
  colAmount: 'Amount paid',
  colCredits: 'Credited',
  colStatus: 'Status',
  colVerifiedAt: 'Payment verified',
  colCreatedAt: 'Date',
  loading: 'Loading...',
  loadError: 'Failed to load purchases',
  retry: 'Retry',
  noPurchases: 'No purchases recorded yet',
  page: (p, total, count) => `Page ${p} of ${total} — ${count} purchases`,
  prev: 'Previous',
  next: 'Next',
}

export const purchasesSectionStrings = dict(FA, EN)
