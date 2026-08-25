import { dict } from '@/lib/adminI18n'

/* Dictionary for ModerationRules.tsx — the regex rule editor for the
 * moderation review queue. */

const FA = {
  loadError: 'خطا در دریافت قوانین پالایش',
  saveErrorGeneric: 'خطا در ذخیره قانون',
  deleteErrorGeneric: 'خطا در حذف قانون',
  savedEdit: 'قانون ویرایش شد',
  savedNew: 'قانون اضافه شد',
  deleted: 'قانون حذف شد',

  rulesTitle: 'قوانین پالایش',
  noRules: 'قانونی ثبت نشده',

  colPattern: 'الگو',
  colCategory: 'دسته‌بندی',
  colSeverity: 'شدت',
  colStatus: 'وضعیت',
  colNotes: 'یادداشت',
  colUpdated: 'به‌روزرسانی',
  colActions: 'عملیات',
  enabled: 'فعال',
  disabled: 'غیرفعال',
  edit: 'ویرایش',
  delete: 'حذف',

  editTitle: 'ویرایش قانون',
  addTitle: 'افزودن قانون جدید',
  formHelp: 'الگو (regex) باید نگارش‌های فارسی، فینگلیش و شکل‌های نویسه‌ای مختلف را پوشش دهد — ی/ي، ک/ك، نیم‌فاصله، و ارقام فارسی/عربی (۰۱۲... و ٠١٢...) در کنار ارقام لاتین.',
  patternLabel: 'الگوی Regex',
  patternPlaceholder: 'مثال: [هه]روئ[یي]ن|hero[iy]n',
  categoryLabel: 'دسته‌بندی',
  categoryPlaceholder: 'مثال: مواد مخدر',
  severityLabel: 'شدت',
  statusLabel: 'وضعیت',
  notesLabel: 'یادداشت',
  notesPlaceholder: 'توضیح دلیل یا زمینه این قانون...',
  update: 'بروزرسانی',
  add: 'افزودن',
  cancel: 'انصراف',
}

const EN: typeof FA = {
  loadError: 'Failed to fetch moderation rules',
  saveErrorGeneric: 'Failed to save the rule',
  deleteErrorGeneric: 'Failed to delete the rule',
  savedEdit: 'Rule updated',
  savedNew: 'Rule added',
  deleted: 'Rule deleted',

  rulesTitle: 'Moderation rules',
  noRules: 'No rules registered',

  colPattern: 'Pattern',
  colCategory: 'Category',
  colSeverity: 'Severity',
  colStatus: 'Status',
  colNotes: 'Notes',
  colUpdated: 'Updated',
  colActions: 'Actions',
  enabled: 'Enabled',
  disabled: 'Disabled',
  edit: 'Edit',
  delete: 'Delete',

  editTitle: 'Edit rule',
  addTitle: 'Add new rule',
  formHelp: 'The pattern (regex) must cover Persian spellings, Finglish and different character forms — ی/ي, ک/ك, the zero-width non-joiner, and Persian/Arabic digit forms (۰۱۲... and ٠١٢...) alongside Latin digits.',
  patternLabel: 'Regex pattern',
  patternPlaceholder: 'Example: [هه]روئ[یي]ن|hero[iy]n',
  categoryLabel: 'Category',
  categoryPlaceholder: 'Example: drugs',
  severityLabel: 'Severity',
  statusLabel: 'Status',
  notesLabel: 'Notes',
  notesPlaceholder: 'Explain the reason or context for this rule...',
  update: 'Update',
  add: 'Add',
  cancel: 'Cancel',
}

export const moderationRulesStrings = dict(FA, EN)
