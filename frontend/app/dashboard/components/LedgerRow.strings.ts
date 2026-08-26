import { dict } from '@/lib/i18n'

const FA = {
  balance: 'موجودی',
}

const EN: typeof FA = {
  balance: 'Balance',
}

export const ledgerRowStrings = dict(FA, EN)
