import { dict } from '@/lib/i18n'

/* ── Comparison ───────────────────────────────────────────────────────────
   Every "sanjabai" cell restates a claim already established elsewhere in
   this content (stats, pricing, hero trust list, FAQ) — nothing new. The
   "subscription" column deliberately stays qualitative and unnamed: no
   competitor, no invented number, just the general pattern those services
   share. */

export interface ComparisonRow {
  label: string
  sanjabai: string
  subscription: string
}

const FA = {
  rows: [
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
  ] satisfies ComparisonRow[],
}

const EN: typeof FA = {
  rows: [
    {
      label: 'Models available',
      sanjabai: '23 models, one account',
      subscription: 'Usually limited to one model family',
    },
    {
      label: 'Payment model',
      sanjabai: 'Pay per use, from a wallet',
      subscription: 'Fixed monthly subscription, even in low-usage months',
    },
    {
      label: 'Unused balance',
      sanjabai: "Never expires — whatever you top up stays there",
      subscription: 'Unused monthly credit is usually forfeited',
    },
    {
      label: 'Access from Iran',
      sanjabai: 'No VPN needed, Iranian card payment',
      subscription: 'Usually needs a VPN and an international card',
    },
    {
      label: 'Connecting to your product',
      sanjabai: 'OpenAI-compatible API; just change the base URL',
      subscription: 'Varies by service',
    },
  ],
}

export const comparisonContent = dict(FA, EN)
