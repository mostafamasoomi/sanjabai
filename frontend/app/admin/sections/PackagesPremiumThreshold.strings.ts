import { dict } from '@/lib/adminI18n'

const FA = {
  serverErrorGeneric: (status: string) => `خطای سرور (${status})`,
  loadError: 'خطا در دریافت آستانهٔ مدل گران',
  saveErrorGeneric: 'ذخیره ناموفق بود',
  saved: 'آستانهٔ مدل گران ذخیره شد',
  loadFailedTitle: 'دریافت آستانهٔ مدل گران ناموفق بود',
  retry: 'تلاش دوباره',
  loading: 'در حال بارگذاری…',
  noData: 'اطلاعاتی یافت نشد',
  fieldLabel: 'مدل گران یعنی قیمت ورودی بیشتر از',
  unit: 'تومان بر میلیون توکن',
  defaultNote: (v: string) => `(پیش‌فرض: ${v})`,
  explain: 'مدلی که قیمت ورودی‌اش بیشتر از این عدد باشد «گران» شمرده می‌شود و فقط سهمیهٔ ستون «از این، روی مدل گران» را مصرف می‌کند.',
  invalid: 'مقدار باید یک عدد صحیح نامنفی باشد.',
  save: 'ذخیره',
  cancel: 'انصراف',
  noChanges: 'تغییری برای ذخیره وجود ندارد',
  rowMissing: 'این تنظیم هنوز در پایگاه داده ساخته نشده — مقدار پیش‌فرض به‌کار می‌رود و اولین ذخیره ردیف را می‌سازد.',
}

const EN: typeof FA = {
  serverErrorGeneric: (status) => `Server error (${status})`,
  loadError: 'Failed to load the premium model threshold',
  saveErrorGeneric: 'Save failed',
  saved: 'Premium model threshold saved',
  loadFailedTitle: 'Failed to load the premium model threshold',
  retry: 'Retry',
  loading: 'Loading…',
  noData: 'No data found',
  fieldLabel: 'A model is premium when its input price exceeds',
  unit: 'Toman per million tokens',
  defaultNote: (v) => `(default: ${v})`,
  explain: 'A model whose input price exceeds this number counts as "premium" and only draws from the "from this, on premium models" column\'s quota.',
  invalid: 'Value must be a non-negative whole number.',
  save: 'Save',
  cancel: 'Cancel',
  noChanges: 'No changes to save',
  rowMissing: 'This setting has not been created in the database yet — the default value is used, and the first save creates the row.',
}

export const packagesPremiumThresholdStrings = dict(FA, EN)
