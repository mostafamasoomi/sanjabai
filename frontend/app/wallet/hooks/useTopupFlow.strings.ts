import { dict } from '@/lib/i18n'

const FA = {
  minAmount: (n: string) => `حداقل مبلغ شارژ ${n} تومان است`,
  maxAmount: (n: string) => `حداکثر مبلغ شارژ ${n} تومان است`,
  redirecting: 'در حال انتقال به درگاه پرداخت...',
  topupError: 'خطا در شارژ',
  purchaseError: 'خطا در خرید بسته',
  serverError: 'خطا در ارتباط با سرور',
  walletTopupDescription: 'شارژ کیف پول',
}

const EN: typeof FA = {
  minAmount: (n) => `The minimum top-up amount is ${n} Toman`,
  maxAmount: (n) => `The maximum top-up amount is ${n} Toman`,
  redirecting: 'Redirecting to the payment gateway...',
  topupError: 'Top-up error',
  purchaseError: 'Error buying package',
  serverError: 'Server connection error',
  walletTopupDescription: 'Wallet top-up',
}

export const useTopupFlowStrings = dict(FA, EN)
