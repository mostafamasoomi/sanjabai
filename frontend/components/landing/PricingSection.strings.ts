import { dict } from '@/lib/i18n'

const FA = {
  eyebrow: 'تعرفه‌ها',
  title: 'فقط بابت آنچه مصرف می‌کنید بپردازید',
  lead: 'اشتراک ماهانه‌ای در کار نیست. کیف پولتان را به تومان شارژ می‌کنید و هزینه‌ی هر درخواست به‌ازای توکن از همان کسر می‌شود.',
  featuredBadge: 'روش اصلی',
  fullRateLink: 'مشاهده‌ی تعرفه‌ی دقیق هر مدل',
}

const EN: typeof FA = {
  eyebrow: 'Pricing',
  title: 'Pay only for what you use',
  lead: "There's no monthly subscription. Top up your wallet in Toman and each request is billed per token from that balance.",
  featuredBadge: 'Main plan',
  fullRateLink: "See the exact rate for every model",
}

export const pricingSectionStrings = dict(FA, EN)
