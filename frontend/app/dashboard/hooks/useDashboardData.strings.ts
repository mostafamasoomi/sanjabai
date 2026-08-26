import { dict } from '@/lib/i18n'

const FA = {
  allFailed: 'خطا در دریافت اطلاعات داشبورد',
  partialFailed: 'برخی اطلاعات بارگذاری نشد',
  serverError: 'خطا در ارتباط با سرور',
}

const EN: typeof FA = {
  allFailed: 'Error loading dashboard data',
  partialFailed: 'Some data failed to load',
  serverError: 'Error connecting to the server',
}

export const useDashboardDataStrings = dict(FA, EN)
