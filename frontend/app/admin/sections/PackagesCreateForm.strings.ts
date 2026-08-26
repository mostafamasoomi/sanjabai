import { dict } from '@/lib/i18n'

const FA = {
  fieldId: 'شناسه (id)',
  fieldNameFa: 'نام فارسی',
  fieldNameEn: 'نام انگلیسی',
  fieldActive: 'فعال',
  fieldBaseAmount: 'مبلغ پرداختی',
  fieldTotalCredits: 'مبلغ واریزی به کیف پول',
  fieldBonusPercent: 'درصد پاداش',
  fieldRequestQuota: 'سهمیهٔ درخواست',
  fieldTokenQuota: 'سهمیهٔ توکن',
  fieldMaxCostPerRequest: 'سقف هزینهٔ هر درخواست',
  fieldRateLimit: 'سقف پیام (۵ ساعته)',
  fieldPremiumRateLimit: 'از این، روی مدل گران (۵ ساعته)',
  fieldValidityDays: 'مدت اعتبار (روز)',
  noQuotaPlaceholder: 'بدون سهمیه',
  noCeilingPlaceholder: 'بدون سقف',
  noExpiryPlaceholder: 'بدون انقضا',
  lossPathWarning: 'سهمیه بدون سقف هزینه — سرور این را رد می‌کند',
  creating: 'در حال ایجاد...',
  createPackage: 'ایجاد بسته',
}

const EN: typeof FA = {
  fieldId: 'Id',
  fieldNameFa: 'Persian name',
  fieldNameEn: 'English name',
  fieldActive: 'Active',
  fieldBaseAmount: 'Amount paid',
  fieldTotalCredits: 'Amount credited to wallet',
  fieldBonusPercent: 'Bonus percent',
  fieldRequestQuota: 'Request quota',
  fieldTokenQuota: 'Token quota',
  fieldMaxCostPerRequest: 'Max cost per request',
  fieldRateLimit: 'Message cap (5-hour window)',
  fieldPremiumRateLimit: 'Of which, on premium models (5-hour window)',
  fieldValidityDays: 'Validity (days)',
  noQuotaPlaceholder: 'No quota',
  noCeilingPlaceholder: 'No ceiling',
  noExpiryPlaceholder: 'No expiry',
  lossPathWarning: 'Quota with no cost ceiling — the server will reject this',
  creating: 'Creating...',
  createPackage: 'Create package',
}

export const packagesCreateFormStrings = dict(FA, EN)
