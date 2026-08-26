import { dict } from '@/lib/i18n'
import type { Lang } from '@/components/LanguageToggle'
import { faNum } from '@/lib/format'
import { useCatalog } from '@/lib/useCatalog'
import { modelCount } from '@/lib/claims'

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

/** Same shape as `ComparisonRow`, but the first row's `sanjabai` cell is a
 *  function of the live model count instead of a fixed string — it used to
 *  hardcode a fixed model count (docs/product-contract.md §4). Resolved to a plain
 *  `ComparisonRow[]` in `useComparisonContent()` below before it reaches the
 *  component. */
type ComparisonRowTemplate = Omit<ComparisonRow, 'sanjabai'> & {
  sanjabai: string | ((count: number | null) => string)
}

const FA = {
  rows: [
    {
      label: 'تعداد مدل‌های در دسترس',
      sanjabai: (count: number | null) => (count != null ? `${faNum(count)} مدل، با یک حساب` : 'مدل‌های متعدد، با یک حساب'),
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
  ] satisfies ComparisonRowTemplate[],
}

const EN: typeof FA = {
  rows: [
    {
      label: 'Models available',
      sanjabai: (count) => (count != null ? `${count} model${count === 1 ? '' : 's'}, one account` : 'Multiple models, one account'),
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

const comparisonContentFor = dict(FA, EN)

/** Resolves the comparison table for a language, filling in the live model
 *  count in the first row — see the hook-inside-a-plain-name note in
 *  Hero.strings.ts. */
function useComparisonContent(lang: Lang): { rows: ComparisonRow[] } {
  const { models, loading } = useCatalog()
  const count = !loading && modelCount(models) > 0 ? modelCount(models) : null
  const base = comparisonContentFor(lang)
  return {
    rows: base.rows.map((row) => ({
      ...row,
      sanjabai: typeof row.sanjabai === 'function' ? row.sanjabai(count) : row.sanjabai,
    })),
  }
}

export const comparisonContent = useComparisonContent
