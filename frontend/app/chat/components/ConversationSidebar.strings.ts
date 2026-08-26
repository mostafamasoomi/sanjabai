import { dict } from '@/lib/i18n'

const FA = {
  newChat: 'چت جدید',
  searchPlaceholder: 'جستجوی مکالمه...',
  clearSearch: 'پاک کردن جستجو',
  noConversationsFound: 'مکالمه‌ای یافت نشد',
  noConversationsYet: 'هنوز مکالمه‌ای ندارید',
  confirmDelete: 'برای تأیید دوباره کلیک کنید',
  delete: 'حذف',
}

const EN: typeof FA = {
  newChat: 'New chat',
  searchPlaceholder: 'Search conversations...',
  clearSearch: 'Clear search',
  noConversationsFound: 'No conversations found',
  noConversationsYet: 'No conversations yet',
  confirmDelete: 'Click again to confirm',
  delete: 'Delete',
}

export const conversationSidebarStrings = dict(FA, EN)
