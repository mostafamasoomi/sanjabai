import { dict } from '@/lib/i18n'

const FA = {
  title: 'تایید شارژ',
  confirmQuestion: 'آیا از شارژ حساب به مبلغ',
  areYouSure: 'اطمینان دارید؟',
  cancel: 'انصراف',
  processing: 'در حال پردازش...',
  confirmAndPay: 'تایید و پرداخت',
}

const EN: typeof FA = {
  title: 'Confirm top-up',
  confirmQuestion: 'Top up your account by',
  areYouSure: 'Are you sure?',
  cancel: 'Cancel',
  processing: 'Processing...',
  confirmAndPay: 'Confirm and pay',
}

export const topupConfirmModalStrings = dict(FA, EN)
