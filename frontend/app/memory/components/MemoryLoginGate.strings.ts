import { dict } from '@/lib/i18n'

const FA = {
  title: 'برای مشاهده حافظه وارد شوید',
  description: 'ابتدا باید وارد حساب خود شوید.',
}

const EN: typeof FA = {
  title: 'Sign in to view memory',
  description: 'You need to sign in to your account first.',
}

export const memoryLoginGateStrings = dict(FA, EN)
