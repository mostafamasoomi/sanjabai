import { dict } from '@/lib/i18n'

const FA = {
  commands: {
    chat: 'چت',
    dashboard: 'داشبورد',
    models: 'مدل‌ها',
    wallet: 'کیف پول',
    pricing: 'تعرفه‌ها',
    playground: 'Playground',
    compare: 'مقایسه مدل‌ها',
    images: 'تولید تصویر',
    profile: 'پروفایل',
    apiKeys: 'کلیدهای API',
    admin: 'پنل مدیریت',
    referral: 'دعوت دوستان',
  },
  categories: {
    navigation: 'ناوبری',
    action: 'عملیات',
    model: 'مدل‌ها',
  },
  searchPlaceholder: 'جستجو در منوها...',
  noResults: 'نتیجه‌ای یافت نشد',
  navigate: 'پیمایش',
  select: 'انتخاب',
  close: 'بستن',
}

const EN: typeof FA = {
  commands: {
    chat: 'Chat',
    dashboard: 'Dashboard',
    models: 'Models',
    wallet: 'Wallet',
    pricing: 'Pricing',
    playground: 'Playground',
    compare: 'Compare models',
    images: 'Image generation',
    profile: 'Profile',
    apiKeys: 'API keys',
    admin: 'Admin panel',
    referral: 'Invite friends',
  },
  categories: {
    navigation: 'Navigation',
    action: 'Actions',
    model: 'Models',
  },
  searchPlaceholder: 'Search menus...',
  noResults: 'No results found',
  navigate: 'navigate',
  select: 'select',
  close: 'close',
}

export const commandPaletteStrings = dict(FA, EN)
