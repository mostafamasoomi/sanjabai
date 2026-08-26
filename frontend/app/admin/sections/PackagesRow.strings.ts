import { dict } from '@/lib/i18n'

const FA = {
  namePlaceholderFa: 'نام فارسی',
  namePlaceholderEn: 'نام انگلیسی',
  hideLegacy: 'بستن فیلدهای قدیمی',
  showLegacy: 'نمایش فیلدهای قدیمی',
  noQuotaPlaceholder: 'بدون سهمیه',
  noCeilingPlaceholder: 'بدون سقف',
  noExpiryPlaceholder: 'بدون انقضا',
  ceilingRequired: 'سقف لازم است',
  save: 'ذخیره',
  legacyNote: 'فیلدهای قدیمی — این‌ها روی مبلغ پرداختی یا واریزی واقعی هیچ اثری ندارند (کد خرید فقط مبلغ پرداختی و مبلغ واریزی بالا را می‌خواند)، صرفاً برای سازگاری با داده‌های قدیمی نگه داشته شده‌اند.',
  fieldDescription: 'توضیحات',
  fieldPriceLegacy: 'price (قدیمی)',
  fieldCreditsLegacy: 'credits (قدیمی)',
  fieldBonusCreditsLegacy: 'bonus_credits (قدیمی)',
}

const EN: typeof FA = {
  namePlaceholderFa: 'Persian name',
  namePlaceholderEn: 'English name',
  hideLegacy: 'Hide legacy fields',
  showLegacy: 'Show legacy fields',
  noQuotaPlaceholder: 'No quota',
  noCeilingPlaceholder: 'No ceiling',
  noExpiryPlaceholder: 'No expiry',
  ceilingRequired: 'A ceiling is required',
  save: 'Save',
  legacyNote: 'Legacy fields — these have no effect on the actual amount charged or credited (checkout only reads the amount paid and amount credited above); kept only for compatibility with old data.',
  fieldDescription: 'Description',
  fieldPriceLegacy: 'price (legacy)',
  fieldCreditsLegacy: 'credits (legacy)',
  fieldBonusCreditsLegacy: 'bonus_credits (legacy)',
}

export const packagesRowStrings = dict(FA, EN)
