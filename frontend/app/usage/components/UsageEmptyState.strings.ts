import { dict } from '@/lib/i18n'

const FA = {
  title: 'هنوز مصرفی ثبت نشده است',
  desc: 'با ارسال اولین پیام در چت، گزارش‌های دقیق مصرف توکن و هزینه اینجا نمایش داده می‌شود.',
  startChat: 'شروع چت',
}

const EN: typeof FA = {
  title: 'No usage recorded yet',
  desc: 'Once you send your first chat message, detailed token and cost reports will show up here.',
  startChat: 'Start chatting',
}

export const usageEmptyStateStrings = dict(FA, EN)
