/* ═══════════════════════════════════════════════════════════════════════════
   Landing copy + data.

   All marketing text lives here rather than being inlined in JSX. One file to
   proofread, one file to hand to a translator, and the section components stay
   readable as layout.
   ═══════════════════════════════════════════════════════════════════════════ */

import type { IconName } from '../ui/Icon'

/* ── Navigation ───────────────────────────────────────────────────────────── */

export const NAV_LINKS = [
  { label: 'امکانات', href: '#features' },
  { label: 'مدل‌ها', href: '/models' },
  { label: 'تعرفه‌ها', href: '#pricing' },
  { label: 'مستندات', href: '/developer' },
] as const

/* ── Hero ─────────────────────────────────────────────────────────────────── */

/**
 * Second line of the headline, rotated in place. Each entry is a complete
 * phrase rather than a bare noun, so the line reads correctly on its own and
 * the swap never leaves a dangling preposition on the line above.
 */
export const HERO_ROTATION = [
  'با یک اشتراک',
  'با یک کلید API',
  'با یک صورتحساب',
] as const

export const HERO_TRUST = [
  'بدون نیاز به کارت اعتباری',
  'پرداخت ریالی',
  'بدون تحریم و بدون فیلترشکن',
] as const

/* ── Hero product preview ─────────────────────────────────────────────────── */

export interface PreviewThread {
  /** Model id shown on the tab. */
  id: string
  label: string
  /** Path to the provider mark in /public/ai. */
  logo: string
  question: string
  answer: string
  latency: string
  cost: string
}

export const PREVIEW_THREADS: PreviewThread[] = [
  {
    id: 'gpt',
    label: 'GPT-4o',
    logo: '/ai/openai.svg',
    question: 'خلاصه‌ی این قرارداد را در سه بند بنویس.',
    answer:
      'سه بند کلیدی قرارداد: ۱) مدت همکاری دوازده ماه با تمدید خودکار، ۲) پرداخت ماهانه تا پنجم هر ماه، ۳) فسخ یک‌طرفه با اعلام سی روز قبل.',
    latency: '۰٫۹ ثانیه',
    cost: '۳۲۰ تومان',
  },
  {
    id: 'claude',
    label: 'Claude',
    logo: '/ai/anthropic.svg',
    question: 'همین سوال را با مدل دیگری بپرس.',
    answer:
      'بدون از دست دادن تاریخچه‌ی گفتگو، مدل را وسط مکالمه عوض کنید. پاسخ بعدی از Claude می‌آید و همان زمینه را می‌بیند.',
    latency: '۱٫۱ ثانیه',
    cost: '۴۱۰ تومان',
  },
  {
    id: 'gemini',
    label: 'Gemini',
    logo: '/ai/googlegemini.svg',
    question: 'این نمودار فروش را تحلیل کن.',
    answer:
      'تصویر، PDF و صفحه‌گسترده را مستقیم آپلود کنید. مدل‌های چندوجهی محتوا را می‌خوانند و تحلیل را در همان مکالمه برمی‌گردانند.',
    latency: '۱٫۴ ثانیه',
    cost: '۲۸۰ تومان',
  },
  {
    id: 'deepseek',
    label: 'DeepSeek',
    logo: '/ai/deepseek.svg',
    question: 'ارزان‌ترین مدل برای این کار کدام است؟',
    answer:
      'مسیریابی هوشمند هر درخواست را به ارزان‌ترین مدلی می‌فرستد که از پس آن برمی‌آید — و هزینه‌ی هر پیام را پیش از ارسال نشان می‌دهد.',
    latency: '۰٫۶ ثانیه',
    cost: '۹۰ تومان',
  },
]

/* ── Provider marquee ─────────────────────────────────────────────────────── */

export const PROVIDERS = [
  { name: 'OpenAI', logo: '/ai/openai.svg' },
  { name: 'Anthropic', logo: '/ai/anthropic.svg' },
  { name: 'Google Gemini', logo: '/ai/googlegemini.svg' },
  { name: 'DeepSeek', logo: '/ai/deepseek.svg' },
  { name: 'Meta', logo: '/ai/meta.svg' },
  { name: 'Mistral', logo: '/ai/mistralai.svg' },
  { name: 'Qwen', logo: '/ai/qwen.svg' },
  { name: 'xAI', logo: '/ai/x.svg' },
  { name: 'Perplexity', logo: '/ai/perplexity.svg' },
  { name: 'Hugging Face', logo: '/ai/huggingface.svg' },
] as const

/* ── Stats ────────────────────────────────────────────────────────────────── */

export const STATS = [
  { value: '+۲۰', label: 'مدل فعال' },
  { value: '۹۹٫۹٪', label: 'در دسترس بودن' },
  { value: '<۱ ثانیه', label: 'میانگین اولین توکن' },
  { value: '۰ تومان', label: 'هزینه‌ی شروع' },
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
    desc: 'وسط مکالمه بین GPT-4o، Claude، Gemini و DeepSeek جابه‌جا شوید. تاریخچه دست‌نخورده می‌ماند و مدل بعدی همان زمینه را می‌بیند — پس برای هر بخش از کار می‌توانید بهترین مدل را انتخاب کنید.',
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
    desc: 'PDF، تصویر و صفحه‌گسترده را آپلود کنید و درباره‌ی محتوایشان سوال بپرسید.',
    href: '/documents',
    linkLabel: 'آپلود سند',
  },
  {
    icon: 'code',
    title: 'API سازگار با OpenAI',
    desc: 'فقط base_url را عوض کنید. SDKهای فعلی‌تان بدون هیچ تغییری کار می‌کنند.',
    href: '/developer',
    linkLabel: 'مستندات API',
  },
  {
    icon: 'chart',
    title: 'هزینه‌ی شفاف',
    desc: 'مصرف توکن و هزینه‌ی هر درخواست به‌صورت لحظه‌ای. هیچ صورتحساب غافلگیرکننده‌ای در کار نیست.',
    href: '/usage',
    linkLabel: 'داشبورد مصرف',
  },
]

/* ── Steps ────────────────────────────────────────────────────────────────── */

export const STEPS = [
  {
    title: 'حساب بسازید',
    desc: 'با ایمیل یا شماره‌ی موبایل ثبت‌نام کنید. اعتبار اولیه‌ی رایگان بلافاصله به کیف پولتان اضافه می‌شود.',
  },
  {
    title: 'مدل را انتخاب کنید',
    desc: 'از میان بیش از بیست مدل یکی را بردارید، یا مسیریابی هوشمند را روشن کنید تا خودش ارزان‌ترین گزینه‌ی مناسب را بردارد.',
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
  Python: `from openai import OpenAI

client = OpenAI(
    base_url="https://api.multiai.ir/v1",
    api_key=os.environ["MULTIAI_API_KEY"],
)

stream = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "سلام!"}],
    stream=True,
)

for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")`,

  JavaScript: `import OpenAI from "openai"

const client = new OpenAI({
  baseURL: "https://api.multiai.ir/v1",
  apiKey: process.env.MULTIAI_API_KEY,
})

const stream = await client.chat.completions.create({
  model: "claude-sonnet-4",
  messages: [{ role: "user", content: "سلام!" }],
  stream: true,
})

for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0]?.delta?.content ?? "")
}`,

  cURL: `curl https://api.multiai.ir/v1/chat/completions \\
  -H "Authorization: Bearer $MULTIAI_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gemini-2.0-flash",
    "messages": [
      { "role": "user", "content": "سلام!" }
    ],
    "stream": true
  }'`,
}

/* ── Pricing ──────────────────────────────────────────────────────────────── */

export interface Plan {
  name: string
  desc: string
  /** Tomans per month. `null` renders as "تماس بگیرید". */
  monthly: number | null
  yearly: number | null
  features: string[]
  cta: string
  href: string
  featured?: boolean
}

export const PLANS: Plan[] = [
  {
    name: 'رایگان',
    desc: 'برای امتحان کردن پلتفرم و کارهای شخصی.',
    monthly: 0,
    yearly: 0,
    features: [
      'دسترسی به ۳ مدل پایه',
      '۱۰۰ پیام در روز',
      'تاریخچه‌ی گفتگو و جستجو',
      'پشتیبانی انجمن کاربران',
    ],
    cta: 'شروع رایگان',
    href: '/signup',
  },
  {
    name: 'حرفه‌ای',
    desc: 'برای کسانی که هر روز با هوش مصنوعی کار می‌کنند.',
    monthly: 390_000,
    yearly: 3_500_000,
    features: [
      'دسترسی به همه‌ی مدل‌ها',
      'پیام نامحدود',
      'ساخت عامل و مهارت اختصاصی',
      'کلید API با سقف مصرف',
      'هوش سند و آپلود فایل',
      'پشتیبانی اولویت‌دار',
    ],
    cta: 'ارتقا به حرفه‌ای',
    href: '/signup',
    featured: true,
  },
  {
    name: 'سازمانی',
    desc: 'برای تیم‌هایی که به جداسازی داده و SLA نیاز دارند.',
    monthly: null,
    yearly: null,
    features: [
      'نمونه‌ی اختصاصی و جداسازی کامل داده',
      'استقرار روی زیرساخت خودتان',
      'ورود یکپارچه (SSO) و کنترل دسترسی',
      'تضمین سطح سرویس و پشتیبانی اختصاصی',
      'فاکتور رسمی و قرارداد سازمانی',
    ],
    cta: 'تماس با فروش',
    href: '/profile',
  },
]

/* ── FAQ ──────────────────────────────────────────────────────────────────── */

export const FAQ = [
  {
    q: 'چه مدل‌هایی در دسترس است؟',
    a: 'خانواده‌ی GPT-4o، Claude، Gemini، DeepSeek، Llama، Mistral، Qwen و چند مدل دیگر — در مجموع بیش از بیست مدل. فهرست کامل با قیمت و اندازه‌ی زمینه‌ی هر مدل در صفحه‌ی مدل‌ها آمده و هر بار که مدل تازه‌ای منتشر شود به همان فهرست اضافه می‌شود.',
  },
  {
    q: 'برای شروع باید هزینه بدهم؟',
    a: 'نه. پلن رایگان همیشگی است: روزی ۱۰۰ پیام روی سه مدل پایه، بدون نیاز به کارت اعتباری. هر وقت خواستید می‌توانید کیف پولتان را شارژ کنید یا به پلن حرفه‌ای بروید.',
  },
  {
    q: 'پرداخت چطور انجام می‌شود؟',
    a: 'با کارت‌های بانکی ایران و به تومان. کیف پول شارژ می‌شود و هزینه‌ی هر درخواست از همان کسر می‌شود؛ مبلغ دقیق هر پیام پیش از ارسال نمایش داده می‌شود. برای مشتریان سازمانی فاکتور رسمی صادر می‌کنیم.',
  },
  {
    q: 'API چطور کار می‌کند؟',
    a: 'API ما با OpenAI سازگار است. کافی است base_url را روی api.multiai.ir/v1 بگذارید و کلید Multiai خودتان را جایگزین کنید؛ بقیه‌ی کد دست‌نخورده باقی می‌ماند. استریم، توابع و embeddings همگی پشتیبانی می‌شوند.',
  },
  {
    q: 'داده‌های من چه می‌شود؟',
    a: 'روی داده‌های شما آموزش نمی‌دهیم و آن‌ها را به‌صورت رمزگذاری‌شده نگهداری می‌کنیم. هر زمان بخواهید می‌توانید تاریخچه‌ی گفتگو را پاک کنید. پلن سازمانی نمونه‌ی اختصاصی با جداسازی کامل داده در اختیارتان می‌گذارد.',
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
