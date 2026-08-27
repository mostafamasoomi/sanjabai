import { dict } from '@/lib/i18n'

/* The reference dictionary for AppShell.tsx -- the highest-traffic file in
   the product (every authenticated page mounts it). Only strings changed
   here; layout, routing and state are untouched. See lib/i18n.ts for why
   `EN: typeof FA` (and no `as const` on FA) is what makes a missing key a
   build error. */

const FA = {
  nav: {
    chat: 'چت',
    models: 'مدل‌ها',
    combos: 'ترکیب‌های من',
    compare: 'مقایسه',
    status: 'وضعیت مدل‌ها',
    dashboard: 'داشبورد',
    wallet: 'کیف پول',
    pricing: 'تعرفه‌ها',
    usage: 'مصرف',
    apiKeys: 'کلید API',
    skills: 'اسکیل‌ها',
    hermes: 'سرور هرمس',
    assistants: 'دستیارها',
    memory: 'حافظه',
    tasks: 'تسک‌ها',
    documents: 'سندساز',
    images: 'تولید تصویر',
    developer: 'توسعه‌دهندگان',
    profile: 'پروفایل',
    referral: 'دعوت',
    admin: 'مدیریت',
  },
  sections: {
    main: 'اصلی',
    tools: 'ابزارها',
    account: 'حساب',
  },
  profile: 'پروفایل',
  dashboard: 'داشبورد',
  logout: 'خروج',
  login: 'ورود',
  signup: 'ثبت‌نام',
  loginSignup: 'ورود / ثبت‌نام',
  menu: 'منو',
  searchMenus: 'جستجو در منوها',
  search: 'جستجو',
  publicNavLabel: 'پیمایش عمومی',
  more: 'بیشتر',
  docs: 'مستندات',
  collapseMenu: 'جمع کردن منو',
  expandMenu: 'باز کردن منو',
}

const EN: typeof FA = {
  nav: {
    chat: 'Chat',
    models: 'Models',
    combos: 'My combos',
    compare: 'Compare',
    status: 'Model status',
    dashboard: 'Dashboard',
    wallet: 'Wallet',
    pricing: 'Pricing',
    usage: 'Usage',
    apiKeys: 'API key',
    skills: 'Skills',
    hermes: 'Hermes server',
    assistants: 'Assistants',
    memory: 'Memory',
    tasks: 'Tasks',
    documents: 'Documents',
    images: 'Image generation',
    developer: 'Developers',
    profile: 'Profile',
    referral: 'Referral',
    admin: 'Admin',
  },
  sections: {
    main: 'Main',
    tools: 'Tools',
    account: 'Account',
  },
  profile: 'Profile',
  dashboard: 'Dashboard',
  logout: 'Log out',
  login: 'Log in',
  signup: 'Sign up',
  loginSignup: 'Log in / Sign up',
  menu: 'Menu',
  searchMenus: 'Search menus',
  search: 'Search',
  publicNavLabel: 'Public navigation',
  more: 'More',
  docs: 'Docs',
  collapseMenu: 'Collapse menu',
  expandMenu: 'Expand menu',
}

export const appShellStrings = dict(FA, EN)
