import { dict } from '@/lib/i18n'
import type { Lang } from '@/components/LanguageToggle'
import { faNum } from '@/lib/format'
import { useCatalog } from '@/lib/useCatalog'
import { modelCount } from '@/lib/claims'

/* pillText/titleHighlight/lead used to hardcode a fixed model count — a number
   that drifts every time a model is added or pulled (docs/product-contract.md
   §4: model-count claims require a live catalog query). All three are now
   functions of the live count, resolved below via useCatalog(). `count` is
   `null` while the catalog is still loading or on fetch failure, in which
   case the copy omits the number rather than flashing "0". `lead` names four
   models by name and used to say "and 19 more" — that "more" count is now
   derived (count - 4, floored at 0) instead of a second hardcoded number. */
const FA = {
  pillText: (count: number | null) =>
    count != null ? `دسترسی مستقیم به ${faNum(count)} مدل پیشرفته` : 'دسترسی مستقیم به مدل‌های پیشرفته',
  titleHighlight: (count: number | null) => (count != null ? `${faNum(count)} مدل هوش مصنوعی،` : 'مدل‌های هوش مصنوعی،'),
  lead: (count: number | null) => {
    const more = count != null ? Math.max(count - 4, 0) : null
    return more != null
      ? `با DeepSeek، Mistral، Gemini، Llama و ${faNum(more)} مدل دیگر در یک فضای کاری فارسی کار کنید. مدل ایده‌آل را بیابید و همه را با یک API به محصول خودتان وصل کنید — با پرداخت به تومان و بدون نیاز به فیلترشکن.`
      : 'با DeepSeek، Mistral، Gemini، Llama و مدل‌های دیگر در یک فضای کاری فارسی کار کنید. مدل ایده‌آل را بیابید و همه را با یک API به محصول خودتان وصل کنید — با پرداخت به تومان و بدون نیاز به فیلترشکن.'
  },
  ctaPrimary: 'شروع رایگان',
  ctaSecondary: 'مشاهده‌ی مدل‌ها',
  previewTabsAria: 'انتخاب مدل',
  youLabel: 'شما',
  unknownAvatar: '؟',
  modelLabel: 'مدل:',
  costNote: 'هزینه‌ی تخمینی هر پیام، پیش از ارسال نمایش داده می‌شود',
}

const EN: typeof FA = {
  pillText: (count) =>
    count != null ? `Direct access to ${count} advanced model${count === 1 ? '' : 's'}` : 'Direct access to advanced models',
  titleHighlight: (count) => (count != null ? `${count} AI model${count === 1 ? '' : 's'},` : 'AI models,'),
  lead: (count) => {
    const more = count != null ? Math.max(count - 4, 0) : null
    return more != null
      ? `Work with DeepSeek, Mistral, Gemini, Llama, and ${more} more model${more === 1 ? '' : 's'} in one Persian-first workspace. Find the ideal model for the job and connect them all to your product with one API — pay in Toman, no VPN needed.`
      : 'Work with DeepSeek, Mistral, Gemini, Llama, and more models in one Persian-first workspace. Find the ideal model for the job and connect them all to your product with one API — pay in Toman, no VPN needed.'
  },
  ctaPrimary: 'Start for free',
  ctaSecondary: 'View models',
  previewTabsAria: 'Select a model',
  youLabel: 'You',
  unknownAvatar: '?',
  modelLabel: 'Model:',
  costNote: 'Estimated cost per message is shown before you send',
}

const heroStringsFor = dict(FA, EN)

type HeroStrings = Omit<ReturnType<typeof heroStringsFor>, 'pillText' | 'titleHighlight' | 'lead'> & {
  pillText: string
  titleHighlight: string
  lead: string
}

/**
 * Resolves the hero copy for a language, filling in the live model count.
 * Named/called exactly like the plain data reader it replaces (`heroStrings(lang)`,
 * called from Hero.tsx's render body) — it just also calls a hook internally
 * (`useCatalog()`), which is fine: hooks only require a stable call order
 * within the enclosing component's render, not a `use`-prefixed name.
 */
function useHeroStrings(lang: Lang): HeroStrings {
  const { models, loading } = useCatalog()
  const count = !loading && modelCount(models) > 0 ? modelCount(models) : null
  const base = heroStringsFor(lang)
  return {
    ...base,
    pillText: base.pillText(count),
    titleHighlight: base.titleHighlight(count),
    lead: base.lead(count),
  }
}

export const heroStrings = useHeroStrings
