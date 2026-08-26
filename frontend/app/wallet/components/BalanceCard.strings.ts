import { dict } from '@/lib/i18n'

const FA = {
  // The unit rendered as its own muted span beside the figure, so it
  // cannot come from f.price() -- but it still belongs here, not in a
  // ternary in the markup.
  tomanUnit: 'تومان',
  currentBalance: 'موجودی فعلی',
  copied: 'کپی شد',
  copy: 'کپی',
}

const EN: typeof FA = {
  tomanUnit: 'Toman',
  currentBalance: 'Current balance',
  copied: 'Copied',
  copy: 'Copy',
}

export const balanceCardStrings = dict(FA, EN)
