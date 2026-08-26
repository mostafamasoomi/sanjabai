import { dict } from '@/lib/i18n'

const FA = {
  loadFailed: 'خطا در بارگذاری اطلاعات پروفایل. لطفاً صفحه را تازه‌سازی کنید.',
  retry: 'تلاش مجدد',
}

const EN: typeof FA = {
  loadFailed: 'Failed to load your profile. Please refresh the page.',
  retry: 'Retry',
}

export const profileErrorBannerStrings = dict(FA, EN)
