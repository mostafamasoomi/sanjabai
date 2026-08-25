import { dict } from '@/lib/adminI18n'

const FA = {
  loadFailed: 'خطا در بارگذاری',
  retry: 'تلاش دوباره',
  refresh: 'بروزرسانی',
}

const EN: typeof FA = {
  loadFailed: 'Failed to load',
  retry: 'Try again',
  refresh: 'Refresh',
}

export const loadStateStrings = dict(FA, EN)
