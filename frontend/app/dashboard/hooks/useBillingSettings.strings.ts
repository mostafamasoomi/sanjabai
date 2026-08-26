import { dict } from '@/lib/i18n'

const FA = {
  paygDisabled: 'پرداخت به ازای مصرف غیرفعال شد',
  paygEnabled: 'پرداخت به ازای مصرف فعال شد',
  settingsError: 'خطا در تغییر تنظیمات',
  serverError: 'خطا در ارتباط با سرور',
  invalidAmount: 'لطفاً مبلغ معتبری وارد کنید',
  hardLimitSet: 'سقف هزینه با موفقیت تنظیم شد',
  hardLimitError: 'خطا در تنظیم سقف هزینه',
}

const EN: typeof FA = {
  paygDisabled: 'Pay-as-you-go disabled',
  paygEnabled: 'Pay-as-you-go enabled',
  settingsError: 'Error changing settings',
  serverError: 'Error connecting to the server',
  invalidAmount: 'Please enter a valid amount',
  hardLimitSet: 'Cost ceiling set successfully',
  hardLimitError: 'Error setting the cost ceiling',
}

export const useBillingSettingsStrings = dict(FA, EN)
