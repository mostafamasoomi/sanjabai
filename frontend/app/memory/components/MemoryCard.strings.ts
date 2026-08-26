import { dict } from '@/lib/i18n'

const FA = {
  tagsPlaceholder: 'برچسب‌ها (با کاما)',
  save: 'ذخیره',
  cancel: 'انصراف',
  manual: 'دستی',
  automatic: 'خودکار',
  edited: (date: string) => `ویرایش: ${date}`,
  edit: 'ویرایش',
  delete: 'حذف',
}

const EN: typeof FA = {
  tagsPlaceholder: 'Tags (comma separated)',
  save: 'Save',
  cancel: 'Cancel',
  manual: 'Manual',
  automatic: 'Automatic',
  edited: (date) => `Edited: ${date}`,
  edit: 'Edit',
  delete: 'Delete',
}

export const memoryCardStrings = dict(FA, EN)
