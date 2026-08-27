import { dict } from '@/lib/i18n'

const FA = {
  title: 'بسته‌ها و موجودی',
  balanceLabel: 'موجودی کیف پول',
  loading: 'در حال بارگذاری…',
  noPackages: 'در حال حاضر بستهٔ فعالی ندارید.',
  activeCountLabel: (count: string) => `${count} بستهٔ فعال`,
  requestsRemainingUnit: 'درخواست باقی‌مانده',
  viewPackages: 'مشاهده بسته‌ها',
}

const EN: typeof FA = {
  title: 'Packages & balance',
  balanceLabel: 'Wallet balance',
  loading: 'Loading…',
  noPackages: 'You have no active package right now.',
  activeCountLabel: (count) => `${count} active package(s)`,
  requestsRemainingUnit: 'requests left',
  viewPackages: 'View packages',
}

export const packagesCardStrings = dict(FA, EN)
