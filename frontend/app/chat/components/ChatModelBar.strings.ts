import { dict } from '@/lib/i18n'

const FA = {
  conversations: 'مکالمات',
  closeSidebar: 'بستن سایدبار',
  openSidebar: 'باز کردن سایدبار',
  modelsLoadError: 'خطا در بارگذاری مدل‌ها',
  smartModePicked: 'مدلی که حالت هوشمند انتخاب کرد',
  compareModels: 'مقایسه مدل‌ها',
  export: 'خروجی گرفتن',
  stop: 'توقف',
}

const EN: typeof FA = {
  conversations: 'Conversations',
  closeSidebar: 'Close sidebar',
  openSidebar: 'Open sidebar',
  modelsLoadError: 'Failed to load models',
  smartModePicked: 'Model picked by Smart Mode',
  compareModels: 'Compare models',
  export: 'Export',
  stop: 'Stop',
}

export const chatModelBarStrings = dict(FA, EN)
