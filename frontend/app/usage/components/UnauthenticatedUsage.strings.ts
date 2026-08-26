import { dict } from '@/lib/i18n'

const FA = {
  title: 'گزارش مصرف',
  desc: 'برای مشاهده گزارش مصرف، ابتدا وارد حساب خود شوید.',
  login: 'ورود',
}

const EN: typeof FA = {
  title: 'Usage report',
  desc: 'Sign in to your account to view your usage report.',
  login: 'Sign in',
}

export const unauthenticatedUsageStrings = dict(FA, EN)
