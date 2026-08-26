import { dict } from '@/lib/i18n'

const FA = {
  pageHeading: 'چت با مدل‌های هوش مصنوعی',
  modelUnavailablePickedDefault: 'مدل درخواستی در دسترس نیست؛ مدل پیش‌فرض انتخاب شد.',
  modelNotFoundPickedDefault: 'مدل درخواستی یافت نشد؛ مدل پیش‌فرض انتخاب شد.',
  catalogLoadError: 'خطا در دریافت فهرست مدل‌ها',
  conversationsDrawerTitle: 'مکالمات',
  noModelsTitle: 'مدلی در دسترس نیست',
  noModelsDescription: 'در حال حاضر فهرست مدل‌ها خالی است. لطفاً اتصال را بررسی کرده و دوباره تلاش کنید.',
  presetsTitle: 'از کجا شروع کنیم؟',
  scrollToBottom: 'اسکرول به پایین',
  attachFile: 'پیوست فایل',
  attachFileHint: 'پیوست فایل (txt, md, csv, json, pdf)',
  webSearch: 'جستجوی وب',
  composerPlaceholder: 'پیام خود را بنویسید... (Shift+Enter برای خط جدید)',
  send: 'ارسال',
  removeAttachment: 'حذف پیوست',
}

const EN: typeof FA = {
  pageHeading: 'Chat with AI models',
  modelUnavailablePickedDefault: 'The requested model is unavailable; the default model was selected.',
  modelNotFoundPickedDefault: 'The requested model was not found; the default model was selected.',
  catalogLoadError: 'Failed to load the model list',
  conversationsDrawerTitle: 'Conversations',
  noModelsTitle: 'No models available',
  noModelsDescription: 'The model list is currently empty. Please check your connection and try again.',
  presetsTitle: 'Where should we start?',
  scrollToBottom: 'Scroll to bottom',
  attachFile: 'Attach file',
  attachFileHint: 'Attach a file (txt, md, csv, json, pdf)',
  webSearch: 'Web search',
  composerPlaceholder: 'Write your message... (Shift+Enter for a new line)',
  send: 'Send',
  removeAttachment: 'Remove attachment',
}

export const chatPageStrings = dict(FA, EN)
