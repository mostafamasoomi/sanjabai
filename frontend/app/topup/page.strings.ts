import { dict } from '@/lib/i18n'

const FA = {
  redirecting: 'در حال انتقال به کیف پول...',
}

const EN: typeof FA = {
  redirecting: 'Redirecting to your wallet...',
}

export const topupPageStrings = dict(FA, EN)
