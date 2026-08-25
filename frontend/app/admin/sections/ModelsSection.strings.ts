import { dict } from '@/lib/adminI18n'

const FA = {
  loadError: 'خطا در دریافت فهرست مدل‌ها',
  saveSuccess: 'مدل پیشفرض سازمان ذخیره شد',
  saveError: 'خطا در ذخیره مدل پیشفرض',
  title: 'مدل‌های فعال',
  subtitle: (n: string) => `${n} مدل در دسترس`,
  cardTitle: 'مدل پیشفرض سازمان',
  cardSubtitle: 'مدلی که کاربران جدید به‌صورت پیشفرض استفاده می‌کنند',
  fieldLabel: 'مدل',
  noDefaultOption: 'بدون مدل پیشفرض (اولین مدل لیست)',
  save: 'ذخیره',
}

const EN: typeof FA = {
  loadError: 'Failed to fetch the model list',
  saveSuccess: 'Organization default model saved',
  saveError: 'Failed to save the default model',
  title: 'Active Models',
  subtitle: (n) => `${n} models available`,
  cardTitle: 'Organization default model',
  cardSubtitle: 'The model new users use by default',
  fieldLabel: 'Model',
  noDefaultOption: 'No default model (first in list)',
  save: 'Save',
}

export const modelsSectionStrings = dict(FA, EN)
