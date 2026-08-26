import { dict } from '@/lib/i18n'

const FA = {
  addMemory: 'افزودن حافظه',
  newMemory: 'حافظه جدید',
  contentPlaceholder: 'محتوای حافظه (مثلاً: زبان برنامه‌نویسی ترجیحی من Python است)',
  tagsPlaceholder: 'برچسب‌ها (با کاما جدا کنید)',
  save: 'ذخیره',
  cancel: 'انصراف',
}

const EN: typeof FA = {
  addMemory: 'Add memory',
  newMemory: 'New memory',
  contentPlaceholder: 'Memory content (e.g. My preferred programming language is Python)',
  tagsPlaceholder: 'Tags (comma separated)',
  save: 'Save',
  cancel: 'Cancel',
}

export const addMemoryFormStrings = dict(FA, EN)
