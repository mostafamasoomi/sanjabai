import { dict } from '@/lib/i18n'

const FA = {
  loadError: 'خطا در دریافت حافظه',
  contentRequired: 'محتوا را وارد کنید',
  saved: 'حافظه ذخیره شد',
  saveError: 'خطا در ذخیره',
  connectionError: 'خطا در ارتباط',
  updated: 'حافظه به‌روزرسانی شد',
  updateError: 'خطا در به‌روزرسانی',
  deleted: 'حافظه حذف شد',
  deleteError: 'خطا در حذف',
}

const EN: typeof FA = {
  loadError: 'Failed to load memory',
  contentRequired: 'Enter the content',
  saved: 'Memory saved',
  saveError: 'Failed to save',
  connectionError: 'Connection error',
  updated: 'Memory updated',
  updateError: 'Failed to update',
  deleted: 'Memory deleted',
  deleteError: 'Failed to delete',
}

export const useMemoriesStrings = dict(FA, EN)
