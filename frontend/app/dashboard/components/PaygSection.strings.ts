import { dict } from '@/lib/i18n'

const FA = {
  title: 'پرداخت به ازای مصرف',
  toggleLabel: 'پرداخت به ازای مصرف (PAYG)',
  enabled: 'فعال',
  disabled: 'غیرفعال',
  hardLimit: 'سقف هزینه',
  hardLimitUnset: 'تعیین نشده',
  hardLimitPlaceholder: 'مبلغ (تومان)',
  save: 'ذخیره',
  saving: '...',
  cancel: 'لغو',
  setHardLimit: 'تنظیم سقف هزینه',
  notifyPct: 'اعلام درصد مصرف',
  infoText: 'با فعال بودن پرداخت به ازای مصرف، از موجودی کیف پول شما کسر می‌شود',
}

const EN: typeof FA = {
  title: 'Pay as you go',
  toggleLabel: 'Pay as you go (PAYG)',
  enabled: 'Enabled',
  disabled: 'Disabled',
  hardLimit: 'Cost ceiling',
  hardLimitUnset: 'Not set',
  hardLimitPlaceholder: 'Amount (Toman)',
  save: 'Save',
  saving: '...',
  cancel: 'Cancel',
  setHardLimit: 'Set a cost ceiling',
  notifyPct: 'Notify at usage %',
  infoText: 'With pay-as-you-go enabled, usage is deducted from your wallet balance',
}

export const paygSectionStrings = dict(FA, EN)
