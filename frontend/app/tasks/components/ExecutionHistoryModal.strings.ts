import { dict } from '@/lib/i18n'

const FA = {
  modalTitle: (taskTitle: string) => `تاریخچه اجرا — ${taskTitle}`,
  empty: 'هنوز اجرایی ثبت نشده است',
  tokens: (n: string) => `${n} توکن`,
}

const EN: typeof FA = {
  modalTitle: (taskTitle) => `Run history — ${taskTitle}`,
  empty: 'No runs recorded yet',
  tokens: (n) => `${n} tokens`,
}

export const executionHistoryModalStrings = dict(FA, EN)
