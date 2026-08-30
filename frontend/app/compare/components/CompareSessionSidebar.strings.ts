import { dict } from '@/lib/i18n'

const FA = {
  historyTitle: 'تاریخچه مقایسه‌ها',
  newComparison: 'مقایسه جدید',
  noSessionsYet: 'هنوز مقایسه‌ای ندارید',
  untitled: 'بدون عنوان',
  confirmDelete: 'برای تأیید دوباره کلیک کنید',
  delete: 'حذف',
}

const EN: typeof FA = {
  historyTitle: 'Compare history',
  newComparison: 'New comparison',
  noSessionsYet: 'No comparisons yet',
  untitled: 'Untitled',
  confirmDelete: 'Click again to confirm',
  delete: 'Delete',
}

export const compareSessionSidebarStrings = dict(FA, EN)
