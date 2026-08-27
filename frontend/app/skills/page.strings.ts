import { dict } from '@/lib/i18n'

const FA = {
  sortOptions: [
    { key: 'popular', label: 'محبوب‌ترین' },
    { key: 'newest', label: 'جدیدترین' },
    { key: 'top_rated', label: 'بهترین امتیاز' },
  ],
  signInTitle: 'وارد شوید',
  signInDesc: 'برای استفاده از مارکتپلیس اسکیل‌ها، ابتدا وارد حساب کاربری خود شوید.',
  signInAction: 'ورود به حساب',
  pageTitle: 'مارکتپلیس اسکیل‌ها',
  pageSubtitle: 'اسکیل‌های آماده رو کشف کن و استفاده کن',
  createNew: 'ایجاد اسکیل جدید',
  searchPlaceholder: 'جستجوی اسکیل...',
  clearAria: 'پاک کردن',
  resultsCount: (n: string) => `${n} اسکیل`,
  emptyTitle: 'اسکیلی یافت نشد',
  emptySearchDesc: 'عبارت جستجو را تغییر دهید یا فیلترها را بررسی کنید.',
  emptyNoneDesc: 'هنوز اسکیلی ایجاد نشده است. اولین اسکیل را شما ایجاد کنید!',
  toastFetchError: 'خطا در دریافت اسکیل‌ها',
  toastServerError: 'خطا در ارتباط با سرور',
}

const EN: typeof FA = {
  sortOptions: [
    { key: 'popular', label: 'Most popular' },
    { key: 'newest', label: 'Newest' },
    { key: 'top_rated', label: 'Top rated' },
  ],
  signInTitle: 'Sign in',
  signInDesc: 'Sign in to your account to use the skills marketplace.',
  signInAction: 'Sign in',
  pageTitle: 'Skills marketplace',
  pageSubtitle: 'Discover and use ready-made skills',
  createNew: 'Create new skill',
  searchPlaceholder: 'Search skills...',
  clearAria: 'Clear',
  resultsCount: (n) => `${n} skills`,
  emptyTitle: 'No skills found',
  emptySearchDesc: 'Try a different search term or check your filters.',
  emptyNoneDesc: 'No skills yet. Create the first one!',
  toastFetchError: 'Failed to load skills',
  toastServerError: 'Server connection error',
}

export const skillsPageStrings = dict(FA, EN)
