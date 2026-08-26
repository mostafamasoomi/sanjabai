import { dict } from '@/lib/i18n'

const FA = {
  title: 'توزیع هزینه مدل‌ها',
  centerLabel: 'تومان',
  noData: 'داده‌ای برای نمایش نمودار وجود ندارد',
}

const EN: typeof FA = {
  title: 'Cost distribution by model',
  centerLabel: 'Toman',
  noData: 'No data to chart',
}

export const modelDistributionCardStrings = dict(FA, EN)
