import { MIN_TOPUP_LABEL } from './constants'

/* ── Pricing ──────────────────────────────────────────────────────────────────
   Sanjabai bills per token against a prepaid wallet — there is no monthly
   subscription. These three columns describe how that works rather than
   inventing tiers, so the page cannot contradict /pricing. */

export interface PricingColumn {
  name: string
  desc: string
  headline: string
  headlineNote?: string
  features: string[]
  cta: string
  href: string
  featured?: boolean
}

export const PRICING_COLUMNS: PricingColumn[] = [
  {
    name: 'ساخت حساب',
    desc: 'برای دیدن پنل، مدل‌ها و مستندات.',
    headline: 'رایگان',
    headlineNote: 'بدون کارت اعتباری',
    features: [
      'دسترسی به پنل و تاریخچه‌ی گفتگو',
      'مشاهده‌ی فهرست و تعرفه‌ی همه‌ی مدل‌ها',
      'ساخت کلید API',
    ],
    cta: 'ثبت‌نام',
    href: '/signup',
  },
  {
    name: 'پرداخت به‌ازای مصرف',
    desc: 'کیف پول را شارژ می‌کنید، بابت توکن پرداخت می‌کنید.',
    headline: 'به‌ازای مصرف',
    headlineNote: `حداقل شارژ ${MIN_TOPUP_LABEL}`,
    features: [
      'قیمت هر مدل جداگانه، به تومان به ازای هر ۱ میلیون توکن',
      'هزینه‌ی تخمینی هر پیام پیش از ارسال',
      'بدون اشتراک ماهانه و بدون انقضای اعتبار',
      'دسترسی به هر ۲۳ مدل',
      'کلید API با سقف مصرف',
    ],
    cta: 'شارژ کیف پول',
    href: '/wallet',
    featured: true,
  },
  {
    name: 'سازمانی',
    desc: 'برای تیم‌هایی که به جداسازی داده و SLA نیاز دارند.',
    headline: 'تماس بگیرید',
    features: [
      'نمونه‌ی اختصاصی و جداسازی کامل داده',
      'استقرار روی زیرساخت خودتان',
      'کنترل دسترسی و مدیریت کاربران',
      'فاکتور رسمی و قرارداد سازمانی',
    ],
    cta: 'تماس با ما',
    href: '/profile',
  },
]
