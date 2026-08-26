import { dict } from '@/lib/i18n'

const FA = {
  title: 'منطقه خطر',
  intro: 'حذف حساب کاربری غیرقابل بازگشت است. تمام داده‌ها و تاریخچه شما حذف خواهد شد.',
  deleteAccount: 'حذف حساب (به‌زودی)',
}

const EN: typeof FA = {
  title: 'Danger Zone',
  intro: 'Account deletion is permanent. All your data and history will be removed.',
  deleteAccount: 'Delete Account (coming soon)',
}

export const dangerZoneSectionStrings = dict(FA, EN)
