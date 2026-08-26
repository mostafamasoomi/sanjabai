import { dict } from '@/lib/i18n'

const FA = {
  // The unit rendered as its own muted span beside the figure, so it
  // cannot come from f.price() -- but it still belongs here, not in a
  // ternary in the markup.
  tomanUnit: 'تومان',
  title: 'تاریخچه تراکنش‌ها',
  filterAll: 'همه',
  filterCredit: 'واریز',
  filterDebit: 'برداشت',
  emptyTitle: 'تراکنشی ثبت نشده',
  emptyDescAll: 'هنوز هیچ تراکنشی انجام نشده است.',
  emptyDescFiltered: 'تراکنشی با این فیلتر یافت نشد.',
  colDate: 'تاریخ',
  colDescription: 'شرح',
  colAmount: 'مبلغ',
  colBalance: 'مانده',
}

const EN: typeof FA = {
  tomanUnit: 'Toman',
  title: 'Transaction History',
  filterAll: 'All',
  filterCredit: 'Credit',
  filterDebit: 'Debit',
  emptyTitle: 'No transactions yet',
  emptyDescAll: 'No transactions have been made yet.',
  emptyDescFiltered: 'No transactions match this filter.',
  colDate: 'Date',
  colDescription: 'Description',
  colAmount: 'Amount',
  colBalance: 'Balance',
}

export const ledgerSectionStrings = dict(FA, EN)
