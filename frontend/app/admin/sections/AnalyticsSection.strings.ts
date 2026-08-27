import { dict } from '@/lib/i18n'

/* Dictionary for the analytics section shell (AnalyticsSection.tsx). The
 * window-scoped chart/table/KPI wording lives with the surface that renders
 * it, in ../components/AnalyticsCharts.strings.ts; this file keeps only the
 * section chrome: the all-time stat cards, the CSV exports, and the
 * load/error states. Same contract as every *.strings.ts (lib/i18n.ts):
 * FA without `as const`, EN annotated `typeof FA`. */

const FA = {
  title: 'تحلیل و درآمد',
  subtitle:
    'درآمد واقعیِ واردشده از درگاه پرداخت، جدا از اعتبارهایی که ادمین دستی شارژ کرده — دو عدد، دو کارت، بدون قاطی‌شدن',
  retry: 'تلاش دوباره',
  loading: 'در حال بارگذاری…',
  loadError: 'دریافت اطلاعات تحلیلی ناموفق بود',
  downloadError: 'دریافت فایل خروجی ناموفق بود',
  allTimeTitle: 'آمار کل از ابتدا',
  totalRevenue: 'درآمد واقعی (پرداخت‌های تکمیل‌شدهٔ درگاه)',
  totalAdminCredit: 'اعتبار دستی ادمین (غیر از درگاه)',
  totalUsers: 'تعداد کاربران',
  totalConversations: 'تعداد گفتگوها',
  trendTitle: 'تحلیل بازه انتخابی',
  exportTitle: 'خروجی داده',
  exportSubtitle: 'دانلود کامل دفتر تراکنش‌ها (ledger) یا فهرست کاربران به صورت CSV',
  exportLedger: 'خروجی دفتر تراکنش‌ها',
  exportUsers: 'خروجی کاربران',
}

const EN: typeof FA = {
  title: 'Analytics & revenue',
  subtitle:
    'Real revenue that came in through the payment gateway, separate from credits the admin topped up by hand — two numbers, two cards, never mixed together',
  retry: 'Retry',
  loading: 'Loading…',
  loadError: 'Failed to load analytics data',
  downloadError: 'Failed to download export file',
  allTimeTitle: 'All-time totals',
  totalRevenue: 'Real revenue (completed gateway payments)',
  totalAdminCredit: 'Manual admin credit (non-gateway)',
  totalUsers: 'Total users',
  totalConversations: 'Total conversations',
  trendTitle: 'Selected window analysis',
  exportTitle: 'Data export',
  exportSubtitle: 'Download the full transaction ledger or the user list as CSV',
  exportLedger: 'Export ledger',
  exportUsers: 'Export users',
}

export const analyticsStrings = dict(FA, EN)
