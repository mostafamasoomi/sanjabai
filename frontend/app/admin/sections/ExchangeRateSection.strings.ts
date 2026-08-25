import { dict } from '@/lib/adminI18n'

const FA = {
  title: 'نرخ ارز',
  subtitle:
    'نرخ زندهٔ دلار به تومان که قیمت همهٔ مدل‌ها بر اساس آن محاسبه می‌شود — نرخ بازار، مارک‌آپ ثابت قابل‌ویرایش، و منابع تأمین (tgju، Bonbast، و هر مرجع دیگری که اضافه کنید)',

  loading: 'در حال بارگذاری…',
  retry: 'تلاش دوباره',
  noData: 'اطلاعاتی یافت نشد',
  loadErrorFallback: 'خطا در دریافت نرخ ارز',

  statBareRate: 'نرخ بازار (بدون مارک‌آپ)',
  statFlatMarkup: 'مارک‌آپ ثابت',
  statEffectiveRate: 'نرخ مؤثر (سرو شده به کاربر)',

  sourceAndTimingTitle: 'منبع و زمان به‌روزرسانی',
  refreshNow: 'واکشی فوری',
  sourceLabel: 'منبع نرخ',
  unhealthyTooltip:
    'وضعیت سالم نیست — این نرخ از یک کش قدیمی یا مقدار ثابت پشتیبان می‌آید، نه بازار زنده',
  unhealthyWarning: '⚠ این وضعیت سالم نیست — نرخ واقعی بازار تأمین نشده',
  lastFetchLabel: 'آخرین واکشی',
  cacheTtlLabel: 'اعتبار کش',
  cacheTtlValue: (n: string) => `${n} ثانیهٔ دیگر`,
  globalMarkupPctLabel: 'درصد سود سراسری فعلی',

  effectiveRateExplanation: (bare: string, flat: string, effective: string) =>
    `نرخ سرو شده به کاربر همیشه برابر است با «نرخ بازار + مارک‌آپ ثابت»: ${bare} + ${flat} = ${effective}. این عدد جدا از درصد سود هر مدل است که روی قیمت پایهٔ همان مدل اعمال می‌شود.`,

  flatMarkupTitle: 'مارک‌آپ ثابت (تومان)',
  flatMarkupDescription: (def: string) =>
    `این عدد به نرخ خام بازار اضافه می‌شود تا نرخ مؤثر ساخته شود — مقدار پیش‌فرض ${def}. صفر مجاز است (یعنی بدون مارک‌آپ ثابت)؛ عدد منفی رد می‌شود چون به فروش زیر نرخ بازار می‌انجامد.`,
  flatMarkupFieldLabel: 'مارک‌آپ ثابت (تومان)',
  save: 'ذخیره',

  sourcesTitle: 'منابع نرخ ارز',
  sourcesDescription:
    'ترتیب تلاش برای واکشی نرخ: override دستی، سپس tgju.org، سپس منابع فعال زیر بر اساس اولویت (عدد کوچک‌تر زودتر امتحان می‌شود)، سپس open.er-api.com، و در نهایت مقدار ثابت در کد.',

  colSource: 'منبع',
  colKind: 'نوع',
  colPriority: 'اولویت',
  colStatus: 'وضعیت',
  colActions: 'عملیات',

  hardcodedKind: 'کد ثابت',
  notEditable: 'غیرقابل‌ویرایش',
  builtinSuffix: ' (پایه)',
  kindBonbast: 'Bonbast',
  kindCustom: (unit: string) => `سفارشی (${unit})`,
  unitRial: 'ریال',
  unitToman: 'تومان',
  enabled: 'فعال',
  disabled: 'غیرفعال',
  deleteTitle: 'حذف',

  addSourceTitle: 'افزودن منبع جدید',
  addSourceDescription:
    'نشانی باید https باشد و به شبکهٔ داخلی سرور اشاره نکند. الگوی استخراج یک عبارت باقاعده با دقیقاً یک گروه () است که عدد نرخ را می‌گیرد — چیزی اجرا نمی‌شود، فقط یک عدد از متن صفحه استخراج می‌شود.',
  fieldKey: 'کلید (انگلیسی، یکتا)',
  fieldDisplayName: 'نام نمایشی',
  fieldUnit: 'واحد',
  fieldPriority: 'اولویت',
  fieldTimeout: 'مهلت زمانی (ثانیه، حداکثر ۱۰)',
  fieldUrl: 'نشانی (https)',
  fieldExtractRegex: 'الگوی استخراج (regex با یک گروه)',
  addSource: 'افزودن منبع',

  // SOURCE_META labels (backend/content.py resolver tiers)
  sourceDbOverride: 'override دستی در پایگاه داده',
  sourceTgju: 'بازار زنده — tgju.org',
  sourceBonbast: 'بازار زنده — Bonbast.com',
  sourceErApi: 'پشتیبان — open.er-api.com',
  sourceHardcodedFallback: 'مقدار ثابت پشتیبان (کد)',
  sourceUnknown: 'نامشخص — کش قدیمی',
  sourceCustom: (name: string) => `منبع سفارشی — ${name}`,

  // Toasts / confirms
  refreshedToast: 'نرخ ارز به‌روزرسانی شد',
  refreshFailedToast: 'به‌روزرسانی نرخ ارز ناموفق بود',
  flatMarkupNegativeToast: 'مارک‌آپ نمی‌تواند منفی باشد',
  flatMarkupSavedToast: 'مارک‌آپ ثابت ذخیره شد',
  flatMarkupSaveFailedToast: 'ذخیرهٔ مارک‌آپ ناموفق بود',
  sourceUpdateFailedToast: 'به‌روزرسانی منبع ناموفق بود',
  confirmDeleteSource: (key: string) => `منبع «${key}» حذف شود؟`,
  sourceDeletedToast: 'منبع حذف شد',
  sourceDeleteFailedToast: 'حذف منبع ناموفق بود',
  newSourceRequiredFieldsToast: 'همهٔ فیلدها به‌جز اولویت و مهلت زمانی الزامی‌اند',
  priorityMustBePositiveToast: 'اولویت باید عددی مثبت باشد',
  timeoutRangeToast: 'مهلت زمانی باید بین ۰ تا ۱۰ ثانیه باشد',
  sourceAddedToast: 'منبع جدید افزوده شد',
  sourceAddFailedToast: 'افزودن منبع ناموفق بود',
}

const EN: typeof FA = {
  title: 'Exchange rate',
  subtitle:
    'The live USD-to-Toman rate every model price is computed from — the market rate, an editable flat markup, and the sources it is fetched from (tgju, Bonbast, and any other source you add)',

  loading: 'Loading…',
  retry: 'Retry',
  noData: 'No data found',
  loadErrorFallback: 'Failed to load the exchange rate',

  statBareRate: 'Market rate (no markup)',
  statFlatMarkup: 'Flat markup',
  statEffectiveRate: 'Effective rate (served to users)',

  sourceAndTimingTitle: 'Source and refresh time',
  refreshNow: 'Fetch now',
  sourceLabel: 'Rate source',
  unhealthyTooltip: 'Not healthy — this rate comes from a stale cache or a hardcoded fallback, not a live market source',
  unhealthyWarning: '⚠ This is not healthy — the real market rate is not being supplied',
  lastFetchLabel: 'Last fetch',
  cacheTtlLabel: 'Cache validity',
  cacheTtlValue: (n) => `${n} seconds left`,
  globalMarkupPctLabel: 'Current global markup percentage',

  effectiveRateExplanation: (bare, flat, effective) =>
    `The rate served to users is always "market rate + flat markup": ${bare} + ${flat} = ${effective}. This is separate from each model's own markup percentage, which applies to that model's base price.`,

  flatMarkupTitle: 'Flat markup (Toman)',
  flatMarkupDescription: (def) =>
    `This value is added to the raw market rate to build the effective rate — default ${def}. Zero is allowed (no flat markup); a negative value is rejected because it would sell below the market rate.`,
  flatMarkupFieldLabel: 'Flat markup (Toman)',
  save: 'Save',

  sourcesTitle: 'Exchange rate sources',
  sourcesDescription:
    'Fetch order: manual override, then tgju.org, then the enabled sources below by priority (lower number tried first), then open.er-api.com, and finally the hardcoded value in code.',

  colSource: 'Source',
  colKind: 'Kind',
  colPriority: 'Priority',
  colStatus: 'Status',
  colActions: 'Actions',

  hardcodedKind: 'Hardcoded',
  notEditable: 'Not editable',
  builtinSuffix: ' (built-in)',
  kindBonbast: 'Bonbast',
  kindCustom: (unit) => `Custom (${unit})`,
  unitRial: 'Rial',
  unitToman: 'Toman',
  enabled: 'Enabled',
  disabled: 'Disabled',
  deleteTitle: 'Delete',

  addSourceTitle: 'Add new source',
  addSourceDescription:
    'The URL must be https and must not point at the internal server network. The extract pattern is a regular expression with exactly one () group that captures the rate number — nothing is executed, only a number is extracted from the page text.',
  fieldKey: 'Key (English, unique)',
  fieldDisplayName: 'Display name',
  fieldUnit: 'Unit',
  fieldPriority: 'Priority',
  fieldTimeout: 'Timeout (seconds, max 10)',
  fieldUrl: 'URL (https)',
  fieldExtractRegex: 'Extract pattern (regex with one group)',
  addSource: 'Add source',

  sourceDbOverride: 'Manual database override',
  sourceTgju: 'Live market — tgju.org',
  sourceBonbast: 'Live market — Bonbast.com',
  sourceErApi: 'Fallback — open.er-api.com',
  sourceHardcodedFallback: 'Hardcoded fallback value (code)',
  sourceUnknown: 'Unknown — stale cache',
  sourceCustom: (name) => `Custom source — ${name}`,

  refreshedToast: 'Exchange rate refreshed',
  refreshFailedToast: 'Failed to refresh the exchange rate',
  flatMarkupNegativeToast: 'Markup cannot be negative',
  flatMarkupSavedToast: 'Flat markup saved',
  flatMarkupSaveFailedToast: 'Failed to save the markup',
  sourceUpdateFailedToast: 'Failed to update the source',
  confirmDeleteSource: (key) => `Delete source "${key}"?`,
  sourceDeletedToast: 'Source deleted',
  sourceDeleteFailedToast: 'Failed to delete the source',
  newSourceRequiredFieldsToast: 'All fields except priority and timeout are required',
  priorityMustBePositiveToast: 'Priority must be a positive number',
  timeoutRangeToast: 'Timeout must be between 0 and 10 seconds',
  sourceAddedToast: 'New source added',
  sourceAddFailedToast: 'Failed to add the source',
}

export const exchangeRateSectionStrings = dict(FA, EN)
