import { dict } from '@/lib/i18n'

const FA = {
  title: (n: string) => `${n} رویداد اخیر`,
  count: (n: string) => `${n} مورد`,
  empty: 'رویدادی ثبت نشده است',
  colModel: 'مدل',
  colInput: 'ورودی',
  colOutput: 'خروجی',
  colCost: 'هزینه',
  colDate: 'تاریخ',
}

const EN: typeof FA = {
  title: (n) => `Last ${n} events`,
  count: (n) => `${n} items`,
  empty: 'No events recorded',
  colModel: 'Model',
  colInput: 'Input',
  colOutput: 'Output',
  colCost: 'Cost',
  colDate: 'Date',
}

export const recentEventsTableStrings = dict(FA, EN)
