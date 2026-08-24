import type { IconName } from '../../ui/Icon'

/* ── Capability showcase (memory / documents / scheduled tasks) ─────────────
   Deeper, tabbed follow-up to the bento grid above for the three features
   least obvious from their one-line card — each mockup below reuses the
   real vocabulary from its own app page (categories, doc types, cron
   presets, delivery channels) rather than inventing sample content. */

export interface CapabilityTab {
  id: string
  icon: IconName
  tabLabel: string
  title: string
  desc: string
  href: string
  linkLabel: string
}

export const CAPABILITY_TABS: CapabilityTab[] = [
  {
    id: 'memory',
    icon: 'cpu',
    tabLabel: 'حافظه‌ی بلندمدت',
    title: 'یک‌بار بگویید، همیشه یادش بماند',
    desc: 'وقتی ترجیح، پروژه یا مهارتی را در گفتگو ذکر می‌کنید، دستیار خودکار آن را دسته‌بندی و ذخیره می‌کند — در گفتگوهای بعدی دوباره لازم نیست از اول توضیح دهید.',
    href: '/memory',
    linkLabel: 'مدیریت حافظه',
  },
  {
    id: 'documents',
    icon: 'palette',
    tabLabel: 'ساخت سند',
    title: 'از پرامپت تا فایل آماده‌ی دانلود',
    desc: 'یک موضوع بدهید، سه فرمت خروجی دارید: پاورپوینت، Word یا اسلاید Markdown — هرکدام با ساختار حرفه‌ای، بدون باز کردن نرم‌افزار دیگری.',
    href: '/documents',
    linkLabel: 'ساخت سند',
  },
  {
    id: 'tasks',
    icon: 'calendar',
    tabLabel: 'وظایف زمان‌بندی‌شده',
    title: 'یک بار زمان‌بندی کنید، همیشه اجرا شود',
    desc: 'پرامپت را روی یک الگوی زمانی ثابت بگذارید تا خودکار اجرا شود و نتیجه‌اش را در داشبورد، ایمیل یا تلگرام دریافت کنید.',
    href: '/tasks',
    linkLabel: 'زمان‌بندی وظیفه',
  },
]

/** app/memory/page.tsx → CATEGORIES. Sample text is illustrative, the same
 * way the hero's PREVIEW_THREADS are — not a claim about any real user. */
export const MEMORY_SAMPLES = [
  { category: 'ترجیحات', text: 'پاسخ‌ها را کوتاه و فهرست‌وار بده' },
  { category: 'پروژه‌ها', text: 'در حال توسعه‌ی یک اپلیکیشن حسابداری هستم' },
  { category: 'مهارت‌ها', text: 'با پایتون و SQL کار می‌کنم' },
] as const

/** app/documents/page.tsx → DOC_TYPES (labels/descriptions reused verbatim). */
export const DOCUMENT_TYPES = [
  { ext: 'PPTX', label: 'پاورپوینت', desc: 'ارائه‌ی حرفه‌ای با اسلایدهای آماده' },
  { ext: 'DOCX', label: 'Word', desc: 'سند متنی با ساختار حرفه‌ای' },
  { ext: 'MD', label: 'اسلاید Markdown', desc: 'خروجی Marp / reveal.js' },
] as const

/** app/tasks/page.tsx → CRON_PRESETS + DELIVERY_CHANNELS. */
export const TASK_SAMPLES = [
  { title: 'خلاصه‌ی اخبار روز', schedule: 'هر روز ساعت ۹ صبح', channel: 'تلگرام' },
  { title: 'گزارش هفتگی وضعیت', schedule: 'هر هفته (دوشنبه)', channel: 'ایمیل' },
] as const
