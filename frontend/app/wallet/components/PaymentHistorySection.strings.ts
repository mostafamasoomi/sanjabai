import { dict } from '@/lib/i18n'

const FA = {
  // The unit rendered as its own muted span beside the figure, so it
  // cannot come from f.price() -- but it still belongs here, not in a
  // ternary in the markup.
  tomanUnit: 'تومان',
  title: 'تاریخچه پرداخت‌ها',
  emptyTitle: 'پرداختی ثبت نشده',
  emptyDesc: 'هنوز پرداختی انجام نشده است.',
  colDate: 'تاریخ',
  colId: 'شناسه',
  colAmount: 'مبلغ',
  colStatus: 'وضعیت',
}

const EN: typeof FA = {
  tomanUnit: 'Toman',
  title: 'Payment History',
  emptyTitle: 'No payments yet',
  emptyDesc: 'No payments have been made yet.',
  colDate: 'Date',
  colId: 'ID',
  colAmount: 'Amount',
  colStatus: 'Status',
}

export const paymentHistorySectionStrings = dict(FA, EN)
