/* ── Hero ─────────────────────────────────────────────────────────────────── */

/**
 * Second line of the headline, rotated in place. Each entry is a complete
 * phrase rather than a bare noun, so the line reads correctly on its own and
 * the swap never leaves a dangling preposition on the line above.
 */
export const HERO_ROTATION = [
  'با یک کیف پول',
  'با یک کلید API',
  'با یک داشبورد',
] as const

export const HERO_TRUST = [
  'بدون اشتراک ماهانه',
  'پرداخت ریالی',
  'بدون نیاز به فیلترشکن',
] as const

/* ── Hero product preview ─────────────────────────────────────────────────── */

export interface PreviewThread {
  id: string
  /** Model id exactly as it appears in litellm_config.yaml. */
  label: string
  /** Provider mark in /public/ai, when one exists for that vendor. */
  logo?: string
  question: string
  answer: string
}

export const PREVIEW_THREADS: PreviewThread[] = [
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
]
