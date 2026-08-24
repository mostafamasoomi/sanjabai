/* ── Comparison ───────────────────────────────────────────────────────────
   Every "sanjabai" cell restates a claim already established elsewhere in
   this file (STATS, PRICING_COLUMNS, HERO_TRUST, FAQ) — nothing new. The
   "subscription" column deliberately stays qualitative and unnamed: no
   competitor, no invented number, just the general pattern those services
   share. */

export interface ComparisonRow {
  label: string
  sanjabai: string
  subscription: string
}

export const COMPARISON_ROWS: ComparisonRow[] = [
  {
    label: 'تعداد مدل‌های در دسترس',
    sanjabai: '۲۳ مدل، با یک حساب',
    subscription: 'معمولاً محدود به یک خانواده‌ی مدل',
  },
  {
    label: 'مدل پرداخت',
    sanjabai: 'پرداخت به‌ازای مصرف، از کیف پول',
    subscription: 'اشتراک ماهانه‌ی ثابت، حتی در ماه‌های کم‌مصرف',
  },
  {
    label: 'اعتبار باقی‌مانده',
    sanjabai: 'بدون انقضا — هرچه شارژ کنید می‌ماند',
    subscription: 'معمولاً اعتبار استفاده‌نشده‌ی هر ماه باطل می‌شود',
  },
  {
    label: 'دسترسی از ایران',
    sanjabai: 'بدون نیاز به فیلترشکن، پرداخت ریالی',
    subscription: 'معمولاً نیاز به فیلترشکن و کارت بین‌المللی',
  },
  {
    label: 'اتصال به محصول شما',
    sanjabai: 'API سازگار با OpenAI؛ فقط آدرس پایه را عوض کنید',
    subscription: 'بسته به سرویس، متفاوت',
  },
] as const
