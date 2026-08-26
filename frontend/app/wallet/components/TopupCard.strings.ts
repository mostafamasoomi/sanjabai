import { dict } from '@/lib/i18n'

const FA = {
  title: 'شارژ حساب',
  customAmountPlaceholder: 'مبلغ دلخواه (تومان)',
  minAmount: (n: string) => `حداقل مبلغ: ${n} تومان`,
  processing: 'در حال پردازش...',
  // `amount` is null when nothing has been entered/selected yet.
  chargeButton: (amount: string | null) => (amount ? `شارژ ${amount} تومان` : 'شارژ حساب'),
}

const EN: typeof FA = {
  title: 'Top up account',
  customAmountPlaceholder: 'Custom amount (Toman)',
  minAmount: (n) => `Minimum amount: ${n} Toman`,
  processing: 'Processing...',
  chargeButton: (amount) => (amount ? `Top up ${amount} Toman` : 'Top up account'),
}

export const topupCardStrings = dict(FA, EN)
