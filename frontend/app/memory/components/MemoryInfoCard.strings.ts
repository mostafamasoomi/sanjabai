import { dict } from '@/lib/i18n'

const FA = {
  title: 'حافظه خودکار',
  body: 'سیستم به‌صورت خودکار اطلاعات مهم شما را از مکالمات استخراج و ذخیره می‌کند. این اطلاعات در چت‌های آینده برای ارائه پاسخ‌های شخصی‌تر استفاده می‌شود.',
}

const EN: typeof FA = {
  title: 'Automatic memory',
  body: 'The system automatically extracts and saves important information from your conversations. This information is used in future chats to provide more personalized answers.',
}

export const memoryInfoCardStrings = dict(FA, EN)
