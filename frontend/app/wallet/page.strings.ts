import { dict } from '@/lib/i18n'

const FA = {
  balanceCopied: 'موجودی کپی شد',
  title: 'کیف پول',
  needLoginTitle: 'کیف پول',
  needLoginDesc: 'برای مشاهده کیف پول، ابتدا وارد حساب خود شوید.',
  login: 'ورود',
  refresh: 'بروزرسانی',
}

const EN: typeof FA = {
  balanceCopied: 'Balance copied',
  title: 'Wallet',
  needLoginTitle: 'Wallet',
  needLoginDesc: 'Sign in to your account to view your wallet.',
  login: 'Sign in',
  refresh: 'Refresh',
}

export const walletPageStrings = dict(FA, EN)
