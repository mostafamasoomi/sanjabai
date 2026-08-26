import { dict } from '@/lib/i18n'

const FA = {
  title: 'وارد شوید',
  desc: 'برای مشاهده داشبورد، ابتدا وارد حساب کاربری خود شوید.',
  login: 'ورود به حساب',
}

const EN: typeof FA = {
  title: 'Sign in',
  desc: 'Sign in to your account to view your dashboard.',
  login: 'Sign in',
}

export const unauthenticatedViewStrings = dict(FA, EN)
