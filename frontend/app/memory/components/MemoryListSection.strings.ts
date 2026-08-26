import { dict } from '@/lib/i18n'

const FA = {
  emptyTitle: 'هنوز حافظه‌ای ذخیره نشده',
  emptyDescription: 'اولین حافظه خود را اضافه کنید یا اجازه دهید سیستم به‌صورت خودکار اطلاعات شما را یاد بگیرد.',
  addMemory: 'افزودن حافظه',
}

const EN: typeof FA = {
  emptyTitle: 'No memory saved yet',
  emptyDescription: 'Add your first memory, or let the system automatically learn about you.',
  addMemory: 'Add memory',
}

export const memoryListSectionStrings = dict(FA, EN)
