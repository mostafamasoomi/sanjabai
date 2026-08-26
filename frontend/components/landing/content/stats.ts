import { dict } from '@/lib/i18n'
import type { Lang } from '@/components/LanguageToggle'
import { faNum } from '@/lib/format'
import { useCatalog } from '@/lib/useCatalog'
import { modelCount } from '@/lib/claims'
import { MIN_TOPUP_LABEL_FA, MIN_TOPUP_LABEL_EN } from './constants'

/* ── Stats ────────────────────────────────────────────────────────────────── */

/* The "active models" stat used to hardcode a fixed number (docs/product-contract.md
   §4: model-count claims require a live catalog query). `value`/`label`
   are now functions of the live count, resolved via useCatalog() below.
   `count` is `null` while the catalog is still loading or on fetch
   failure — the value falls back to "—", same as faNum's own fallback. */
const FA = {
  items: [
    {
      value: (count: number | null) => (count != null ? faNum(count) : '—'),
      label: (_count: number | null) => 'مدل فعال',
    },
    { value: () => 'تومان', label: () => 'واحد پرداخت' },
    { value: () => '۰', label: () => 'هزینه‌ی اشتراک ماهانه' },
    { value: () => MIN_TOPUP_LABEL_FA, label: () => 'حداقل شارژ کیف پول' },
  ],
}

const EN: typeof FA = {
  items: [
    {
      value: (count) => (count != null ? String(count) : '—'),
      label: (count) => (count === 1 ? 'active model' : 'active models'),
    },
    { value: () => 'Toman', label: () => 'payment currency' },
    { value: () => '0', label: () => 'monthly subscription fee' },
    { value: () => MIN_TOPUP_LABEL_EN, label: () => 'minimum wallet top-up' },
  ],
}

const statsContentFor = dict(FA, EN)

/** Resolves the stats band for a language, filling in the live model count
 *  — see the hook-inside-a-plain-name note in Hero.strings.ts. */
function useStatsContent(lang: Lang) {
  const { models, loading } = useCatalog()
  const count = !loading && modelCount(models) > 0 ? modelCount(models) : null
  const base = statsContentFor(lang)
  return { items: base.items.map((item) => ({ value: item.value(count), label: item.label(count) })) }
}

export const statsContent = useStatsContent
