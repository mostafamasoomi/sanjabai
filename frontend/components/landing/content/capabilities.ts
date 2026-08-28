import { dict } from '@/lib/i18n'
import type { Lang } from '@/components/LanguageToggle'
import { useLandingOverrides, applyModuleOverride } from '@/lib/landingOverrides'
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

const FA = {
  tabs: [
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
  ] satisfies CapabilityTab[],

  /** app/memory/page.tsx → CATEGORIES. Sample text is illustrative, the same
   * way the hero's previewThreads are — not a claim about any real user. */
  memorySamples: [
    { category: 'ترجیحات', text: 'پاسخ‌ها را کوتاه و فهرست‌وار بده' },
    { category: 'پروژه‌ها', text: 'در حال توسعه‌ی یک اپلیکیشن حسابداری هستم' },
    { category: 'مهارت‌ها', text: 'با پایتون و SQL کار می‌کنم' },
  ],

  /** app/documents/page.tsx → DOC_TYPES (labels/descriptions reused verbatim). */
  documentTypes: [
    { ext: 'PPTX', label: 'پاورپوینت', desc: 'ارائه‌ی حرفه‌ای با اسلایدهای آماده' },
    { ext: 'DOCX', label: 'Word', desc: 'سند متنی با ساختار حرفه‌ای' },
    { ext: 'MD', label: 'اسلاید Markdown', desc: 'خروجی Marp / reveal.js' },
  ],

  /** app/tasks/page.tsx → CRON_PRESETS + DELIVERY_CHANNELS. */
  taskSamples: [
    { title: 'خلاصه‌ی اخبار روز', schedule: 'هر روز ساعت ۹ صبح', channel: 'تلگرام' },
    { title: 'گزارش هفتگی وضعیت', schedule: 'هر هفته (دوشنبه)', channel: 'ایمیل' },
  ],
}

const EN: typeof FA = {
  tabs: [
    {
      id: 'memory',
      icon: 'cpu',
      tabLabel: 'Long-term memory',
      title: 'Say it once, it remembers forever',
      desc: 'When you mention a preference, project, or skill in chat, the assistant automatically categorizes and saves it — no need to explain it again in later conversations.',
      href: '/memory',
      linkLabel: 'Manage memory',
    },
    {
      id: 'documents',
      icon: 'palette',
      tabLabel: 'Document generation',
      title: 'From prompt to downloadable file',
      desc: 'Give a topic, get three output formats: PowerPoint, Word, or a Markdown slide deck — each professionally structured, no other software required.',
      href: '/documents',
      linkLabel: 'Generate a document',
    },
    {
      id: 'tasks',
      icon: 'calendar',
      tabLabel: 'Scheduled tasks',
      title: 'Schedule it once, it runs forever',
      desc: 'Put a prompt on a fixed schedule to run automatically and get the result on your dashboard, by email, or on Telegram.',
      href: '/tasks',
      linkLabel: 'Schedule a task',
    },
  ],

  memorySamples: [
    { category: 'Preferences', text: 'Keep answers short and in bullet points' },
    { category: 'Projects', text: "I'm building an accounting app" },
    { category: 'Skills', text: 'I work with Python and SQL' },
  ],

  documentTypes: [
    { ext: 'PPTX', label: 'PowerPoint', desc: 'A professional presentation with ready-made slides' },
    { ext: 'DOCX', label: 'Word', desc: 'A professionally structured text document' },
    { ext: 'MD', label: 'Markdown slides', desc: 'Marp / reveal.js output' },
  ],

  taskSamples: [
    { title: "Today's news summary", schedule: 'Every day at 9am', channel: 'Telegram' },
    { title: 'Weekly status report', schedule: 'Every week (Monday)', channel: 'Email' },
  ],
}

const capabilitiesContentFor = dict(FA, EN)

/** Resolves the capability showcase for a language, applying any
 *  admin-stored override. */
function useCapabilitiesContent(lang: Lang) {
  const overrides = useLandingOverrides()
  return applyModuleOverride('capabilities', lang, capabilitiesContentFor(lang), overrides)
}

export const capabilitiesContent = useCapabilitiesContent

/** Today's static FA/EN values — admin editor placeholders only, see the
 *  matching comment in hero.ts. */
export const capabilitiesStaticDefaults = { fa: FA, en: EN }
