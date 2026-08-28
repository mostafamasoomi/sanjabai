import { dict } from '@/lib/i18n'
import type { Lang } from '@/components/LanguageToggle'
import { useLandingOverrides, applyModuleOverride } from '@/lib/landingOverrides'

/* ── Hero ─────────────────────────────────────────────────────────────────── */

export interface PreviewThread {
  id: string
  /** Model id exactly as it appears in litellm_config.yaml. Latin in both languages. */
  label: string
  /** Provider mark in /public/ai, when one exists for that vendor. */
  logo?: string
  question: string
  answer: string
}

const FA = {
  /**
   * Second line of the headline, rotated in place. Each entry is a complete
   * phrase rather than a bare noun, so the line reads correctly on its own
   * and the swap never leaves a dangling preposition on the line above.
   */
  rotation: ['با یک کیف پول', 'با یک کلید API', 'با یک داشبورد'],

  trust: ['بدون اشتراک ماهانه', 'پرداخت ریالی', 'بدون نیاز به فیلترشکن'],

  /** Hero product preview. Sample text is illustrative, not a claim about
   *  any real conversation. */
  previewThreads: [
    {
      id: 'deepseek',
      label: 'deepseek-v4-pro',
      logo: '/ai/deepseek.svg',
      question: 'خلاصه‌ی این قرارداد را در سه بند بنویس.',
      answer:
        'سه بند کلیدی قرارداد: ۱) مدت همکاری دوازده ماه با تمدید خودکار، ۲) پرداخت ماهانه تا پنجم هر ماه، ۳) فسخ یک‌طرفه با اعلام سی روز قبل.',
    },
    {
      id: 'mistral',
      label: 'mistral-large',
      logo: '/ai/mistralai.svg',
      question: 'همین سوال را با مدل دیگری بپرس.',
      answer:
        'بدون از دست دادن تاریخچه‌ی گفتگو، مدل را وسط مکالمه عوض کنید. پاسخ بعدی از مدل تازه می‌آید و همان زمینه را می‌بیند.',
    },
    {
      id: 'gemini',
      label: 'gemini-3.5-flash',
      logo: '/ai/googlegemini.svg',
      question: 'این نمودار فروش را تحلیل کن.',
      answer:
        'تصویر و سند را مستقیم آپلود کنید. مدل‌های چندوجهی محتوا را می‌خوانند و تحلیل را در همان مکالمه برمی‌گردانند.',
    },
    {
      id: 'llama',
      label: 'llama-3.3-70b',
      logo: '/ai/meta.svg',
      question: 'ارزان‌ترین مدل برای این کار کدام است؟',
      answer:
        'حالت هوشمند هر درخواست را به مناسب‌ترین مدل می‌فرستد، و هزینه‌ی تخمینی هر پیام پیش از ارسال کنار کادر نوشتن نمایش داده می‌شود.',
    },
  ] satisfies PreviewThread[],
}

const EN: typeof FA = {
  rotation: ['with one wallet', 'with one API key', 'with one dashboard'],

  trust: ['No monthly subscription', 'Iranian bank card payment', 'No VPN needed'],

  previewThreads: [
    {
      id: 'deepseek',
      label: 'deepseek-v4-pro',
      logo: '/ai/deepseek.svg',
      question: 'Summarize this contract in three points.',
      answer:
        "Three key points: 1) a twelve-month term with automatic renewal, 2) monthly payment due by the 5th, 3) either party can terminate with 30 days' notice.",
    },
    {
      id: 'mistral',
      label: 'mistral-large',
      logo: '/ai/mistralai.svg',
      question: 'Ask the same question with a different model.',
      answer:
        'Switch models mid-conversation without losing history. The next reply comes from the new model and sees the same context.',
    },
    {
      id: 'gemini',
      label: 'gemini-3.5-flash',
      logo: '/ai/googlegemini.svg',
      question: 'Analyze this sales chart.',
      answer:
        'Upload the image or document directly. Multimodal models read the content and return the analysis in the same conversation.',
    },
    {
      id: 'llama',
      label: 'llama-3.3-70b',
      logo: '/ai/meta.svg',
      question: 'Which model is cheapest for this task?',
      answer:
        'Smart mode routes each request to the best-fit model, and the estimated cost per message shows next to the input box before you send.',
    },
  ],
}

const heroContentFor = dict(FA, EN)

/** Resolves hero copy for a language, applying any admin-stored content
 *  override — see the hook-inside-a-plain-name note in comparison.ts's
 *  useComparisonContent. */
function useHeroContent(lang: Lang) {
  const overrides = useLandingOverrides()
  return applyModuleOverride('hero', lang, heroContentFor(lang), overrides)
}

export const heroContent = useHeroContent

/** Today's static FA/EN values, unresolved by any override — used only as
 *  the admin editor's placeholders (LandingContentSection.tsx), never to
 *  render the public page. Hero has no live-count-dependent leaf, so this
 *  is exactly what a visitor sees with an empty override store. */
export const heroStaticDefaults = { fa: FA, en: EN }
