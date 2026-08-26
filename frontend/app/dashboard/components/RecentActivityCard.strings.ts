import { dict } from '@/lib/i18n'

const FA = {
  title: 'فعالیت اخیر',
  viewAll: 'مشاهده همه',
  emptyTitle: 'هنوز تراکنشی ثبت نشده است',
  emptyDesc: 'پس از اولین شارژ یا مصرف، تراکنش‌ها اینجا فهرست می‌شوند.',
  topUp: 'شارژ کیف پول',
}

const EN: typeof FA = {
  title: 'Recent activity',
  viewAll: 'View all',
  emptyTitle: 'No transactions recorded yet',
  emptyDesc: 'Once you top up or spend, your transactions will be listed here.',
  topUp: 'Top up wallet',
}

export const recentActivityCardStrings = dict(FA, EN)
