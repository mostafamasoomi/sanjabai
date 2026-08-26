import { dict } from '@/lib/i18n'

const FA = {
  navAria: 'پیمایش اصلی',
  signIn: 'ورود',
  signUp: 'شروع رایگان',
  openMenuAria: 'باز کردن منو',
  closeMenuAria: 'بستن منو',
  menuDialogAria: 'منوی پیمایش',
  drawerSignIn: 'ورود به حساب',
}

const EN: typeof FA = {
  navAria: 'Main navigation',
  signIn: 'Sign in',
  signUp: 'Start for free',
  openMenuAria: 'Open menu',
  closeMenuAria: 'Close menu',
  menuDialogAria: 'Navigation menu',
  drawerSignIn: 'Sign in to your account',
}

export const landingHeaderStrings = dict(FA, EN)
