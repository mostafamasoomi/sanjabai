import { dict } from '@/lib/adminI18n'

const FA = {
  title: 'تحلیل و درآمد',
  subtitle:
    'درآمد واقعیِ واردشده از درگاه پرداخت، جدا از اعتبارهایی که ادمین دستی شارژ کرده — دو عدد، دو کارت، بدون قاطی‌شدن',
  retry: 'تلاش دوباره',
  loading: 'در حال بارگذاری…',
  loadError: 'دریافت اطلاعات تحلیلی ناموفق بود',
  downloadError: 'دریافت فایل خروجی ناموفق بود',
  totalRevenue: 'درآمد واقعی (پرداخت‌های تکمیل‌شدهٔ درگاه)',
  totalAdminCredit: 'اعتبار دستی ادمین (غیر از درگاه)',
  totalUsers: 'تعداد کاربران',
  totalConversations: 'تعداد گفتگوها',
  trend30d: 'روند ۳۰ روز اخیر',
  noChartData: 'داده‌ای برای رسم نمودار ثبت نشده است',
  consumptionLegend: (total: string) => `مصرف کاربران (charged_amount) — مجموع ${total}`,
  gatewayLegend: (total: string) => `درآمد واقعی درگاه (پرداخت‌های تکمیل‌شده) — مجموع ${total}`,
  chartExplainer: (days: string) =>
    `مصرف یعنی چه مبلغی بابت استفاده از مدل‌ها از کاربران کسر شده — نه لزوماً پولی که وارد درگاه شده. برای ${days} روز اخیر، این دو عدد آگاهانه جدا از هم رسم شده‌اند تا با هم اشتباه گرفته نشوند.`,
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
  totalRevenue: 'Real revenue (completed gateway payments)',
  totalAdminCredit: 'Manual admin credit (non-gateway)',
  totalUsers: 'Total users',
  totalConversations: 'Total conversations',
  trend30d: 'Last 30 days trend',
  noChartData: 'No data recorded to draw a chart',
  consumptionLegend: (total) => `User consumption (charged_amount) — total ${total}`,
  gatewayLegend: (total) => `Real gateway revenue (completed payments) — total ${total}`,
  chartExplainer: (days) =>
    `Consumption is how much was charged to users for using models — not necessarily money that reached the gateway. For the last ${days} days, these two numbers are deliberately plotted apart so they cannot be mistaken for each other.`,
  exportTitle: 'Data export',
  exportSubtitle: 'Download the full transaction ledger or the user list as CSV',
  exportLedger: 'Export ledger',
  exportUsers: 'Export users',
}

export const analyticsStrings = dict(FA, EN)
