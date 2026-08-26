import { dict } from '@/lib/i18n'
import type { Lang } from '@/components/LanguageToggle'
import { faNum } from '@/lib/format'
import { useCatalog } from '@/lib/useCatalog'
import { modelCount } from '@/lib/claims'

/* See the identical note in Hero.strings.ts: this used to hardcode a fixed
   model count (docs/product-contract.md §4). `count` is `null` while the catalog
   is still loading or on fetch failure, in which case the label omits the
   number instead of flashing "0". */
const FA = {
  label: (count: number | null) => (count != null ? `${faNum(count)} مدل، از یک پنل` : 'مدل‌های متعدد، از یک پنل'),
}

const EN: typeof FA = {
  label: (count) =>
    count != null ? `${count} model${count === 1 ? '' : 's'}, one dashboard` : 'Multiple models, one dashboard',
}

const providerMarqueeStringsFor = dict(FA, EN)

/** Resolves the marquee label for a language, filling in the live model
 *  count — see the hook-inside-a-plain-name note in Hero.strings.ts. */
function useProviderMarqueeStrings(lang: Lang): { label: string } {
  const { models, loading } = useCatalog()
  const count = !loading && modelCount(models) > 0 ? modelCount(models) : null
  return { label: providerMarqueeStringsFor(lang).label(count) }
}

export const providerMarqueeStrings = useProviderMarqueeStrings
