import { dict } from '@/lib/i18n'
import type { Lang } from '@/components/LanguageToggle'
import { faNum } from '@/lib/format'
import { useCatalog } from '@/lib/useCatalog'
import { modelCount } from '@/lib/claims'
import { MIN_TOPUP_LABEL_FA, MIN_TOPUP_LABEL_EN } from './constants'

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

/** Same shape as `PricingColumn`, but one `features` line ("Access to all
 *  N models") is a function of the live model count instead of a fixed
 *  string (docs/product-contract.md §4). Resolved to a plain
 *  `PricingColumn[]` in `usePricingContent()` below before it reaches the
 *  component. */
type FeatureLine = string | ((count: number | null) => string)
type PricingColumnTemplate = Omit<PricingColumn, 'features'> & { features: FeatureLine[] }

const FA = {
  columns: [
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
      headlineNote: `حداقل شارژ ${MIN_TOPUP_LABEL_FA}`,
      features: [
        'قیمت هر مدل جداگانه، به تومان به ازای هر ۱ میلیون توکن',
        'هزینه‌ی تخمینی هر پیام پیش از ارسال',
        'بدون اشتراک ماهانه و بدون انقضای اعتبار',
        (count: number | null) => (count != null ? `دسترسی به هر ${faNum(count)} مدل` : 'دسترسی به همه‌ی مدل‌ها'),
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
  ] satisfies PricingColumnTemplate[],
}

const EN: typeof FA = {
  columns: [
    {
      name: 'Create an account',
      desc: 'To view the dashboard, models, and docs.',
      headline: 'Free',
      headlineNote: 'No credit card',
      features: [
        'Access to the dashboard and chat history',
        'View the list and pricing of every model',
        'Create an API key',
      ],
      cta: 'Sign up',
      href: '/signup',
    },
    {
      name: 'Pay as you go',
      desc: 'Top up your wallet, pay per token.',
      headline: 'Pay per use',
      headlineNote: `${MIN_TOPUP_LABEL_EN} minimum top-up`,
      features: [
        'Separate price per model, in Toman per 1M tokens',
        'Estimated cost per message shown before sending',
        'No monthly subscription, balance never expires',
        (count) => (count != null ? `Access to all ${count} model${count === 1 ? '' : 's'}` : 'Access to all models'),
        'API key with a usage cap',
      ],
      cta: 'Top up wallet',
      href: '/wallet',
      featured: true,
    },
    {
      name: 'Enterprise',
      desc: 'For teams that need data isolation and an SLA.',
      headline: 'Contact us',
      features: [
        'Dedicated instance with full data isolation',
        'Deploy on your own infrastructure',
        'Access control and user management',
        'Formal invoicing and an enterprise contract',
      ],
      cta: 'Contact us',
      href: '/profile',
    },
  ],
}

const pricingContentFor = dict(FA, EN)

/** Resolves the pricing columns for a language, filling in the live model
 *  count in the "Access to all N models" feature line — see the
 *  hook-inside-a-plain-name note in Hero.strings.ts. */
function usePricingContent(lang: Lang): { columns: PricingColumn[] } {
  const { models, loading } = useCatalog()
  const count = !loading && modelCount(models) > 0 ? modelCount(models) : null
  const base = pricingContentFor(lang)
  return {
    columns: base.columns.map((column) => ({
      ...column,
      features: column.features.map((line) => (typeof line === 'function' ? line(count) : line)),
    })),
  }
}

export const pricingContent = usePricingContent
