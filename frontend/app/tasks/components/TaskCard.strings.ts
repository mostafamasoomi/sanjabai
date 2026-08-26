import { dict } from '@/lib/i18n'

const FA = {
  disable: 'غیرفعال کردن',
  enable: 'فعال کردن',
  active: 'فعال',
  inactive: 'غیرفعال',
  runCount: (n: string) => `اجرا: ${n} بار`,
  lastRun: (when: string) => `آخرین اجرا: ${when}`,
  nextRun: (when: string) => `اجرای بعدی: ${when}`,
  run: 'اجرا',
  history: 'تاریخچه',
  edit: 'ویرایش',
  delete: 'حذف',
}

const EN: typeof FA = {
  disable: 'Disable',
  enable: 'Enable',
  active: 'Active',
  inactive: 'Inactive',
  runCount: (n) => `Runs: ${n}`,
  lastRun: (when) => `Last run: ${when}`,
  nextRun: (when) => `Next run: ${when}`,
  run: 'Run',
  history: 'History',
  edit: 'Edit',
  delete: 'Delete',
}

export const taskCardStrings = dict(FA, EN)
