/* ═══════════════════════════════════════════════════════════════════════════
   Landing copy + data.

   All marketing text lives here rather than being inlined in JSX. One file to
   proofread, one file to hand to a translator, and the section components stay
   readable as layout.

   ───────────────────────────────────────────────────────────────────────────
   Every factual claim below is sourced from the codebase, not invented:

   - Model list        backend/litellm_config.yaml  (23 chat models)
   - API base URL      app/developer/page.tsx       (https://sanjabai.ir/v1)
   - Billing model     app/pricing/page.tsx         (per-token, wallet, no
                                                     monthly subscription)
   - Top-up amounts    app/wallet/page.tsx          (PRESET_AMOUNTS, MIN_TOPUP)

   If you add a claim here, make sure something in the repo backs it up.
   ═══════════════════════════════════════════════════════════════════════════ */

import type { IconName } from '../ui/Icon'

/** Documented in app/developer/page.tsx. Not `api.sanjabai.ir`. */
export const API_BASE_URL = 'https://sanjabai.ir/v1'

/** app/wallet/page.tsx → MIN_TOPUP */
export const MIN_TOPUP_LABEL = '۱۰ هزار تومان'

/* ── Navigation ───────────────────────────────────────────────────────────── */

export const NAV_LINKS = [
  { label: 'امکانات', href: '#features' },
  { label: 'مدل‌ها', href: '/models' },
  { label: 'تعرفه‌ها', href: '/pricing' },
  { label: 'مستندات', href: '/developer' },
] as const

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

/* ── Model marquee ────────────────────────────────────────────────────────────
   The real catalog from backend/litellm_config.yaml. Vendors whose mark is not
   in /public/ai simply render as a name — better than borrowing a logo that
   has nothing to do with the model. */

export const CATALOG = [
  { name: 'deepseek-v4-pro', logo: '/ai/deepseek.svg' },
  { name: 'mistral-large', logo: '/ai/mistralai.svg' },
  { name: 'gemini-3.5-flash', logo: '/ai/googlegemini.svg' },
  { name: 'llama-3.3-70b', logo: '/ai/meta.svg' },
  { name: 'gpt-oss-120b', logo: '/ai/openai.svg' },
  { name: 'tencent-hy3' },
  { name: 'mimo-v2.5' },
  { name: 'kimi-k2.7-code' },
  { name: 'deepseek-v4-flash', logo: '/ai/deepseek.svg' },
  { name: 'gemma-4-31b-it', logo: '/ai/googlegemini.svg' },
  { name: 'mistral-medium-3-5', logo: '/ai/mistralai.svg' },
  { name: 'agnes-2.0-flash' },
] as const

/* ── Stats ────────────────────────────────────────────────────────────────── */

export const STATS = [
  { value: '۲۳', label: 'مدل فعال' },
  { value: 'تومان', label: 'واحد پرداخت' },
  { value: '۰', label: 'هزینه‌ی اشتراک ماهانه' },
  { value: MIN_TOPUP_LABEL, label: 'حداقل شارژ کیف پول' },
] as const

/* ── Features ─────────────────────────────────────────────────────────────── */

export interface Feature {
  icon: IconName
  title: string
  desc: string
  href?: string
  linkLabel?: string
}

export const FEATURES: Feature[] = [
  {
    icon: 'chat',
    title: 'چت چندمدلی، بدون قطع شدن رشته‌ی گفتگو',
    desc: 'وسط مکالمه بین مدل‌ها جابه‌جا شوید. تاریخچه دست‌نخورده می‌ماند و مدل بعدی همان زمینه را می‌بیند — پس برای هر بخش از کار می‌توانید مناسب‌ترین مدل را انتخاب کنید.',
    href: '/chat',
    linkLabel: 'باز کردن چت',
  },
  {
    icon: 'sparkles',
    title: 'عامل‌هایی که کار را تا آخر می‌برند',
    desc: 'عامل بسازید، به آن مهارت و حافظه‌ی بلندمدت بدهید و ابزارهایتان را وصل کنید. کارهای تکراری را زمان‌بندی کنید و نتیجه را در داشبورد ببینید.',
    href: '/skills',
    linkLabel: 'ساخت عامل',
  },
  {
    icon: 'compare',
    title: 'مقایسه‌ی کنار هم',
    desc: 'یک پرامپت، چند مدل. کیفیت، سرعت و هزینه را در یک نگاه بسنجید.',
    href: '/compare',
    linkLabel: 'مقایسه کنید',
  },
  {
    icon: 'file',
    title: 'هوش سند',
    desc: 'سند و تصویر را آپلود کنید و درباره‌ی محتوایشان سوال بپرسید.',
    href: '/documents',
    linkLabel: 'آپلود سند',
  },
  {
    icon: 'code',
    title: 'API سازگار با OpenAI',
    desc: 'فقط آدرس پایه را عوض کنید. SDKهای فعلی‌تان بدون تغییری کار می‌کنند.',
    href: '/developer',
    linkLabel: 'مستندات API',
  },
  {
    icon: 'cpu',
    title: 'حافظه‌ای که خودش می‌سازد',
    desc: 'ترجیحات، پروژه‌ها و مهارت‌هایی که در گفتگو می‌گویید، خودکار به‌عنوان حافظه‌ی بلندمدت ذخیره می‌شود — از دفعه‌ی بعد لازم نیست دوباره توضیح دهید.',
    href: '/memory',
    linkLabel: 'مدیریت حافظه',
  },
  {
    icon: 'palette',
    title: 'خروجی آماده: پاورپوینت، Word و اسلاید',
    desc: 'یک پرامپت بدهید، فایل PPTX، Word یا اسلاید Markdown آماده‌ی دانلود بگیرید — بدون باز کردن نرم‌افزار جدا.',
    href: '/documents',
    linkLabel: 'ساخت سند',
  },
  {
    icon: 'calendar',
    title: 'وظایف زمان‌بندی‌شده',
    desc: 'یک پرامپت را روی بازه‌ی دلخواه (روزانه، هفتگی، هر چند ساعت) زمان‌بندی کنید و نتیجه را در داشبورد، ایمیل یا تلگرام دریافت کنید.',
    href: '/tasks',
    linkLabel: 'زمان‌بندی وظیفه',
  },
  {
    icon: 'chart',
    title: 'هزینه‌ی شفاف، بدون اشتراک ماهانه',
    desc: 'کیف پولتان را شارژ می‌کنید و هزینه‌ی هر درخواست به‌ازای توکن از همان کسر می‌شود. مصرف و مانده را لحظه‌ای در داشبورد می‌بینید.',
    href: '/usage',
    linkLabel: 'داشبورد مصرف',
  },
]

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

/* ── Comparison ───────────────────────────────────────────────────────────
   Every "sanjabai" cell restates a claim already established elsewhere in
   this file (STATS, PRICING_COLUMNS, HERO_TRUST, FAQ) — nothing new. The
   "subscription" column deliberately stays qualitative and unnamed: no
   competitor, no invented number, just the general pattern those services
   share. */

export interface ComparisonRow {
  label: string
  sanjabai: string
  subscription: string
}

export const COMPARISON_ROWS: ComparisonRow[] = [
  {
    label: 'تعداد مدل‌های در دسترس',
    sanjabai: '۲۳ مدل، با یک حساب',
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
] as const

/* ── Steps ────────────────────────────────────────────────────────────────── */

export const STEPS = [
  {
    title: 'حساب بسازید',
    desc: 'با ایمیل ثبت‌نام کنید. ساخت حساب رایگان است و هیچ کارت اعتباری‌ای لازم ندارد.',
  },
  {
    title: 'کیف پول را شارژ کنید',
    desc: `از ${MIN_TOPUP_LABEL} به بالا، با کارت بانکی ایرانی. هر مبلغی که شارژ کنید تا وقتی مصرف نشود سر جایش می‌ماند.`,
  },
  {
    title: 'وصل شوید یا شروع به چت کنید',
    desc: 'در مرورگر کار کنید، یا یک کلید API بسازید و همان مدل‌ها را به محصول خودتان وصل کنید.',
  },
] as const

/* ── API section ──────────────────────────────────────────────────────────── */

export const API_POINTS = [
  'همان مسیرهای /v1/chat/completions و /v1/embeddings',
  'پاسخ استریمی با Server-Sent Events',
  'کلید اختصاصی برای هر سرویس، با سقف مصرف جداگانه',
] as const

export const CODE_SAMPLES: Record<string, string> = {
  Python: `import os

from openai import OpenAI

client = OpenAI(
    base_url="${API_BASE_URL}",
    api_key=os.environ["SANJABAI_API_KEY"],
)

stream = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[{"role": "user", "content": "سلام!"}],
    stream=True,
)

for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")`,

  JavaScript: `import OpenAI from "openai"

const client = new OpenAI({
  baseURL: "${API_BASE_URL}",
  apiKey: process.env.SANJABAI_API_KEY,
})

const stream = await client.chat.completions.create({
  model: "mistral-large",
  messages: [{ role: "user", content: "سلام!" }],
  stream: true,
})

for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0]?.delta?.content ?? "")
}`,

  cURL: `curl ${API_BASE_URL}/chat/completions \\
  -H "Authorization: Bearer $SANJABAI_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gemini-3.5-flash",
    "messages": [
      { "role": "user", "content": "سلام!" }
    ],
    "stream": true
  }'`,
}

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

export const PRICING_COLUMNS: PricingColumn[] = [
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
    headlineNote: `حداقل شارژ ${MIN_TOPUP_LABEL}`,
    features: [
      'قیمت هر مدل جداگانه، به تومان به ازای هر ۱ میلیون توکن',
      'هزینه‌ی تخمینی هر پیام پیش از ارسال',
      'بدون اشتراک ماهانه و بدون انقضای اعتبار',
      'دسترسی به هر ۲۳ مدل',
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
]

/* ── FAQ ──────────────────────────────────────────────────────────────────── */

export const FAQ = [
  {
    q: 'چه مدل‌هایی در دسترس است؟',
    a: 'در حال حاضر ۲۳ مدل گفتگو، از جمله DeepSeek V4، Mistral Large، Gemini Flash، Llama 3.3، GPT-OSS، Gemma، MiMo، Kimi و Tencent Hy3. فهرست کامل به همراه تعرفه و اندازه‌ی زمینه‌ی هر مدل در صفحه‌ی مدل‌ها آمده است.',
  },
  {
    q: 'چطور هزینه محاسبه می‌شود؟',
    a: 'به‌ازای توکن. هر مدل قیمت ورودی و خروجی جداگانه‌ای به تومان به ازای هر یک میلیون توکن دارد. کیف پولتان را شارژ می‌کنید و هزینه‌ی هر درخواست از همان کسر می‌شود؛ خبری از اشتراک ماهانه نیست.',
  },
  {
    q: 'برای شروع باید هزینه بدهم؟',
    a: `ساخت حساب رایگان است و برای دیدن پنل، فهرست مدل‌ها و مستندات هیچ پرداختی لازم نیست. برای ارسال درخواست به مدل‌ها باید کیف پول را شارژ کنید؛ حداقل مبلغ شارژ ${MIN_TOPUP_LABEL} است.`,
  },
  {
    q: 'پرداخت چطور انجام می‌شود؟',
    a: 'با کارت‌های بانکی ایران و به تومان. مبالغ پیشنهادی شارژ ۱۰۰ هزار، ۵۰۰ هزار، ۱ میلیون و ۵ میلیون تومان است، ولی می‌توانید هر مبلغ دلخواهی وارد کنید. برای مشتریان سازمانی فاکتور رسمی صادر می‌شود.',
  },
  {
    q: 'API چطور کار می‌کند؟',
    a: `API ما با OpenAI سازگار است. کافی است آدرس پایه را روی ${API_BASE_URL} بگذارید و کلید Sanjabai خودتان را جایگزین کنید؛ بقیه‌ی کد دست‌نخورده باقی می‌ماند. استریم و embeddings هم پشتیبانی می‌شوند.`,
  },
  {
    q: 'به فیلترشکن نیاز دارم؟',
    a: 'خیر. درخواست‌ها از زیرساخت ما به مدل‌ها می‌رود، پس از داخل ایران و بدون هیچ ابزار جانبی کار می‌کند — چه در مرورگر و چه از طریق API.',
  },
] as const

/* ── Footer ───────────────────────────────────────────────────────────────── */

export const FOOTER_COLUMNS = [
  {
    title: 'محصول',
    links: [
      { label: 'چت', href: '/chat' },
      { label: 'مدل‌ها', href: '/models' },
      { label: 'مقایسه‌ی مدل‌ها', href: '/compare' },
      { label: 'عامل‌ها و مهارت‌ها', href: '/skills' },
      { label: 'تعرفه‌ها', href: '/pricing' },
    ],
  },
  {
    title: 'توسعه‌دهندگان',
    links: [
      { label: 'مستندات API', href: '/developer' },
      { label: 'کلیدهای API', href: '/api-keys' },
      { label: 'زمین بازی', href: '/playground' },
      { label: 'گزارش مصرف', href: '/usage' },
    ],
  },
  {
    title: 'حساب کاربری',
    links: [
      { label: 'ورود', href: '/login' },
      { label: 'ثبت‌نام', href: '/signup' },
      { label: 'کیف پول', href: '/wallet' },
      { label: 'دعوت دوستان', href: '/referral' },
    ],
  },
] as const
