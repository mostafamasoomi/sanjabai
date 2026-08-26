import { dict } from '@/lib/i18n'

const FA = {
  loadFailed: 'خطا در بارگذاری مکالمه',
  deleteFailed: 'خطا در حذف مکالمه',
  selectConversationFirst: 'ابتدا یک مکالمه را انتخاب کنید',
  fileDownloaded: 'فایل دانلود شد',
  exportFailed: 'خطا در خروجی گرفتن',
}

const EN: typeof FA = {
  loadFailed: 'Failed to load the conversation',
  deleteFailed: 'Failed to delete the conversation',
  selectConversationFirst: 'Select a conversation first',
  fileDownloaded: 'File downloaded',
  exportFailed: 'Export failed',
}

export const useConversationsStrings = dict(FA, EN)
