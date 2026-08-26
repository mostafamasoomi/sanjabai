import { dict } from '@/lib/i18n'

const FA = {
  title: 'گزارش مصرف',
  subtitle: 'تحلیل هزینه، توکن و عملکرد مدل‌ها',
  exportCsv: 'خروجی CSV',
  refresh: 'بروزرسانی',
  scopeNote: 'آمار این ماه',
}

const EN: typeof FA = {
  title: 'Usage report',
  subtitle: 'Cost, token, and model performance breakdown',
  exportCsv: 'Export CSV',
  refresh: 'Refresh',
  scopeNote: 'This month’s stats',
}

export const usageHeaderStrings = dict(FA, EN)
