import type { LandingModuleKey } from '../../lib/landingOverrides'

/**
 * Fixture data for landingOverrides.test.ts, split into its own file only to
 * stay under the 500-line-per-file house rule (the test file itself is the
 * behavior; this is just data).
 *
 * Today's real resolved content -- copied verbatim from
 * components/landing/content/*.ts, i.e. the FA/EN objects AFTER `dict()`
 * picks a language and (for the four count-dependent modules) after the
 * function leaves have already been resolved with a `count` -- exactly the
 * shape `applyModuleOverride` receives from its call sites.
 */

const API_BASE_URL = 'https://sanjabai.com/v1'
const MIN_TOPUP_LABEL_FA = '۱۰ هزار تومان'
const MIN_TOPUP_LABEL_EN = '10,000 Toman'

export const STATIC_FIXTURES: Record<LandingModuleKey, { fa: unknown; en: unknown }> = {
  api: {
    fa: {
      points: [
        'همان مسیرهای /v1/chat/completions و /v1/embeddings',
        'پاسخ استریمی با Server-Sent Events',
        'کلید اختصاصی برای هر سرویس، با سقف مصرف جداگانه',
      ],
      codeSamples: {
        Python: `import os\n\nclient = OpenAI(base_url="${API_BASE_URL}")`,
        JavaScript: `const client = new OpenAI({ baseURL: "${API_BASE_URL}" })`,
        cURL: `curl ${API_BASE_URL}/chat/completions`,
      },
    },
    en: {
      points: [
        'The same /v1/chat/completions and /v1/embeddings routes',
        'Streamed responses over Server-Sent Events',
        'A dedicated key per service, each with its own usage cap',
      ],
      codeSamples: {
        Python: `import os\n\nclient = OpenAI(base_url="${API_BASE_URL}")`,
        JavaScript: `const client = new OpenAI({ baseURL: "${API_BASE_URL}" })`,
        cURL: `curl ${API_BASE_URL}/chat/completions`,
      },
    },
  },
  capabilities: {
    fa: {
      tabs: [
        { id: 'memory', icon: 'cpu', tabLabel: 'حافظه‌ی بلندمدت', title: 'یک‌بار بگویید، همیشه یادش بماند', desc: 'وقتی ترجیح، پروژه یا مهارتی را در گفتگو ذکر می‌کنید...', href: '/memory', linkLabel: 'مدیریت حافظه' },
        { id: 'documents', icon: 'palette', tabLabel: 'ساخت سند', title: 'از پرامپت تا فایل آماده‌ی دانلود', desc: 'یک موضوع بدهید، سه فرمت خروجی دارید...', href: '/documents', linkLabel: 'ساخت سند' },
        { id: 'tasks', icon: 'calendar', tabLabel: 'وظایف زمان‌بندی‌شده', title: 'یک بار زمان‌بندی کنید، همیشه اجرا شود', desc: 'پرامپت را روی یک الگوی زمانی ثابت بگذارید...', href: '/tasks', linkLabel: 'زمان‌بندی وظیفه' },
      ],
      memorySamples: [
        { category: 'ترجیحات', text: 'پاسخ‌ها را کوتاه و فهرست‌وار بده' },
        { category: 'پروژه‌ها', text: 'در حال توسعه‌ی یک اپلیکیشن حسابداری هستم' },
        { category: 'مهارت‌ها', text: 'با پایتون و SQL کار می‌کنم' },
      ],
      documentTypes: [
        { ext: 'PPTX', label: 'پاورپوینت', desc: 'ارائه‌ی حرفه‌ای با اسلایدهای آماده' },
        { ext: 'DOCX', label: 'Word', desc: 'سند متنی با ساختار حرفه‌ای' },
        { ext: 'MD', label: 'اسلاید Markdown', desc: 'خروجی Marp / reveal.js' },
      ],
      taskSamples: [
        { title: 'خلاصه‌ی اخبار روز', schedule: 'هر روز ساعت ۹ صبح', channel: 'تلگرام' },
        { title: 'گزارش هفتگی وضعیت', schedule: 'هر هفته (دوشنبه)', channel: 'ایمیل' },
      ],
    },
    en: {
      tabs: [
        { id: 'memory', icon: 'cpu', tabLabel: 'Long-term memory', title: 'Say it once, it remembers forever', desc: 'When you mention a preference...', href: '/memory', linkLabel: 'Manage memory' },
        { id: 'documents', icon: 'palette', tabLabel: 'Document generation', title: 'From prompt to downloadable file', desc: 'Give a topic, get three output formats...', href: '/documents', linkLabel: 'Generate a document' },
        { id: 'tasks', icon: 'calendar', tabLabel: 'Scheduled tasks', title: 'Schedule it once, it runs forever', desc: 'Put a prompt on a fixed schedule...', href: '/tasks', linkLabel: 'Schedule a task' },
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
    },
  },
  catalog: { fa: { CATALOG: [{ name: 'deepseek-v4-pro', logo: '/ai/deepseek.svg' }] }, en: { CATALOG: [{ name: 'deepseek-v4-pro', logo: '/ai/deepseek.svg' }] } },
  comparison: {
    fa: {
      rows: [
        { label: 'تعداد مدل‌های در دسترس', sanjabai: '۲۴ مدل، با یک حساب', subscription: 'معمولاً محدود به یک خانواده‌ی مدل' },
        { label: 'مدل پرداخت', sanjabai: 'پرداخت به‌ازای مصرف، از کیف پول', subscription: 'اشتراک ماهانه‌ی ثابت، حتی در ماه‌های کم‌مصرف' },
        { label: 'اعتبار باقی‌مانده', sanjabai: 'بدون انقضا — هرچه شارژ کنید می‌ماند', subscription: 'معمولاً اعتبار استفاده‌نشده‌ی هر ماه باطل می‌شود' },
        { label: 'دسترسی از ایران', sanjabai: 'بدون نیاز به فیلترشکن، پرداخت ریالی', subscription: 'معمولاً نیاز به فیلترشکن و کارت بین‌المللی' },
        { label: 'اتصال به محصول شما', sanjabai: 'API سازگار با OpenAI؛ فقط آدرس پایه را عوض کنید', subscription: 'بسته به سرویس، متفاوت' },
      ],
    },
    en: {
      rows: [
        { label: 'Models available', sanjabai: '24 models, one account', subscription: 'Usually limited to one model family' },
        { label: 'Payment model', sanjabai: 'Pay per use, from a wallet', subscription: 'Fixed monthly subscription, even in low-usage months' },
        { label: 'Unused balance', sanjabai: 'Never expires — whatever you top up stays there', subscription: 'Unused monthly credit is usually forfeited' },
        { label: 'Access from Iran', sanjabai: 'No VPN needed, Iranian card payment', subscription: 'Usually needs a VPN and an international card' },
        { label: 'Connecting to your product', sanjabai: 'OpenAI-compatible API; just change the base URL', subscription: 'Varies by service' },
      ],
    },
  },
  constants: { fa: { MIN_TOPUP_LABEL_FA }, en: { MIN_TOPUP_LABEL_EN } },
  faq: {
    fa: {
      items: [
        { q: 'چه مدل‌هایی در دسترس است؟', a: 'در حال حاضر ۲۴ مدل گفتگو...' },
        { q: 'چطور هزینه محاسبه می‌شود؟', a: 'به‌ازای توکن. هر مدل قیمت ورودی و خروجی جداگانه‌ای دارد.' },
        { q: 'برای شروع باید هزینه بدهم؟', a: `ساخت حساب رایگان است... حداقل مبلغ شارژ ${MIN_TOPUP_LABEL_FA} است.` },
        { q: 'پرداخت چطور انجام می‌شود؟', a: 'با کارت‌های بانکی ایران و به تومان.' },
        { q: 'API چطور کار می‌کند؟', a: `آدرس پایه را روی ${API_BASE_URL} بگذارید.` },
        { q: 'به فیلترشکن نیاز دارم؟', a: 'خیر. درخواست‌ها از زیرساخت ما به مدل‌ها می‌رود.' },
      ],
    },
    en: {
      items: [
        { q: 'Which models are available?', a: '24 chat models today...' },
        { q: 'How is cost calculated?', a: 'Per token. Each model has separate input and output prices.' },
        { q: 'Do I have to pay to get started?', a: `Creating an account is free... the minimum top-up is ${MIN_TOPUP_LABEL_EN}.` },
        { q: 'How does payment work?', a: 'With Iranian bank cards, in Toman.' },
        { q: 'How does the API work?', a: `Just point the base URL to ${API_BASE_URL}.` },
        { q: 'Do I need a VPN?', a: 'No. Requests go from our infrastructure to the models.' },
      ],
    },
  },
  features: {
    fa: {
      items: [
        { icon: 'chat', title: 'چت چندمدلی، بدون قطع شدن رشته‌ی گفتگو', desc: 'وسط مکالمه بین مدل‌ها جابه‌جا شوید.', href: '/chat', linkLabel: 'باز کردن چت' },
        { icon: 'sparkles', title: 'عامل‌هایی که کار را تا آخر می‌برند', desc: 'عامل بسازید، به آن مهارت و حافظه بدهید.', href: '/skills', linkLabel: 'ساخت عامل' },
      ],
    },
    en: {
      items: [
        { icon: 'chat', title: 'Multi-model chat, one unbroken thread', desc: 'Switch models mid-conversation.', href: '/chat', linkLabel: 'Open chat' },
        { icon: 'sparkles', title: 'Agents that see the job through', desc: 'Build an agent, give it skills and memory.', href: '/skills', linkLabel: 'Build an agent' },
      ],
    },
  },
  footer: {
    fa: {
      columns: [
        { title: 'محصول', links: [{ label: 'چت', href: '/chat' }, { label: 'مدل‌ها', href: '/models' }] },
        { title: 'توسعه‌دهندگان', links: [{ label: 'مستندات API', href: '/developer' }] },
      ],
    },
    en: {
      columns: [
        { title: 'Product', links: [{ label: 'Chat', href: '/chat' }, { label: 'Models', href: '/models' }] },
        { title: 'Developers', links: [{ label: 'API docs', href: '/developer' }] },
      ],
    },
  },
  hero: {
    fa: {
      rotation: ['با یک کیف پول', 'با یک کلید API', 'با یک داشبورد'],
      trust: ['بدون اشتراک ماهانه', 'پرداخت ریالی', 'بدون نیاز به فیلترشکن'],
      previewThreads: [
        { id: 'deepseek', label: 'deepseek-v4-pro', logo: '/ai/deepseek.svg', question: 'خلاصه‌ی این قرارداد را در سه بند بنویس.', answer: 'سه بند کلیدی قرارداد...' },
        { id: 'mistral', label: 'mistral-large', logo: '/ai/mistralai.svg', question: 'همین سوال را با مدل دیگری بپرس.', answer: 'بدون از دست دادن تاریخچه...' },
        { id: 'gemini', label: 'gemini-3.5-flash', logo: '/ai/googlegemini.svg', question: 'این نمودار فروش را تحلیل کن.', answer: 'تصویر و سند را مستقیم آپلود کنید.' },
        { id: 'llama', label: 'llama-3.3-70b', logo: '/ai/meta.svg', question: 'ارزان‌ترین مدل برای این کار کدام است؟', answer: 'حالت هوشمند هر درخواست را می‌فرستد.' },
      ],
    },
    en: {
      rotation: ['with one wallet', 'with one API key', 'with one dashboard'],
      trust: ['No monthly subscription', 'Iranian bank card payment', 'No VPN needed'],
      previewThreads: [
        { id: 'deepseek', label: 'deepseek-v4-pro', logo: '/ai/deepseek.svg', question: 'Summarize this contract in three points.', answer: 'Three key points...' },
        { id: 'mistral', label: 'mistral-large', logo: '/ai/mistralai.svg', question: 'Ask the same question with a different model.', answer: 'Switch models mid-conversation without losing history.' },
        { id: 'gemini', label: 'gemini-3.5-flash', logo: '/ai/googlegemini.svg', question: 'Analyze this sales chart.', answer: 'Upload the image or document directly.' },
        { id: 'llama', label: 'llama-3.3-70b', logo: '/ai/meta.svg', question: 'Which model is cheapest for this task?', answer: 'Smart mode routes each request to the best-fit model.' },
      ],
    },
  },
  nav: {
    fa: { links: [{ label: 'امکانات', href: '#features' }, { label: 'مدل‌ها', href: '/models' }, { label: 'تعرفه‌ها', href: '/pricing' }, { label: 'مستندات', href: '/developer' }] },
    en: { links: [{ label: 'Features', href: '#features' }, { label: 'Models', href: '/models' }, { label: 'Pricing', href: '/pricing' }, { label: 'Docs', href: '/developer' }] },
  },
  pricing: {
    fa: {
      columns: [
        { name: 'ساخت حساب', desc: 'برای دیدن پنل، مدل‌ها و مستندات.', headline: 'رایگان', headlineNote: 'بدون کارت اعتباری', features: ['دسترسی به پنل و تاریخچه‌ی گفتگو', 'مشاهده‌ی فهرست و تعرفه‌ی همه‌ی مدل‌ها', 'ساخت کلید API'], cta: 'ثبت‌نام', href: '/signup' },
        { name: 'پرداخت به‌ازای مصرف', desc: 'کیف پول را شارژ می‌کنید، بابت توکن پرداخت می‌کنید.', headline: 'به‌ازای مصرف', headlineNote: `حداقل شارژ ${MIN_TOPUP_LABEL_FA}`, features: ['قیمت هر مدل جداگانه', 'هزینه‌ی تخمینی هر پیام پیش از ارسال', 'بدون اشتراک ماهانه و بدون انقضای اعتبار', 'دسترسی به هر ۲۴ مدل', 'کلید API با سقف مصرف'], cta: 'شارژ کیف پول', href: '/wallet', featured: true },
        { name: 'سازمانی', desc: 'برای تیم‌هایی که به جداسازی داده و SLA نیاز دارند.', headline: 'تماس بگیرید', features: ['نمونه‌ی اختصاصی و جداسازی کامل داده', 'استقرار روی زیرساخت خودتان', 'کنترل دسترسی و مدیریت کاربران', 'فاکتور رسمی و قرارداد سازمانی'], cta: 'تماس با ما', href: '/profile' },
      ],
    },
    en: {
      columns: [
        { name: 'Create an account', desc: 'To view the dashboard, models, and docs.', headline: 'Free', headlineNote: 'No credit card', features: ['Access to the dashboard and chat history', 'View the list and pricing of every model', 'Create an API key'], cta: 'Sign up', href: '/signup' },
        { name: 'Pay as you go', desc: 'Top up your wallet, pay per token.', headline: 'Pay per use', headlineNote: `${MIN_TOPUP_LABEL_EN} minimum top-up`, features: ['Separate price per model', 'Estimated cost per message shown before sending', 'No monthly subscription, balance never expires', 'Access to all 24 models', 'API key with a usage cap'], cta: 'Top up wallet', href: '/wallet', featured: true },
        { name: 'Enterprise', desc: 'For teams that need data isolation and an SLA.', headline: 'Contact us', features: ['Dedicated instance with full data isolation', 'Deploy on your own infrastructure', 'Access control and user management', 'Formal invoicing and an enterprise contract'], cta: 'Contact us', href: '/profile' },
      ],
    },
  },
  stats: {
    fa: { items: [{ value: '۲۴', label: 'مدل فعال' }, { value: 'تومان', label: 'واحد پرداخت' }, { value: '۰', label: 'هزینه‌ی اشتراک ماهانه' }, { value: MIN_TOPUP_LABEL_FA, label: 'حداقل شارژ کیف پول' }] },
    en: { items: [{ value: '24', label: 'active models' }, { value: 'Toman', label: 'payment currency' }, { value: '0', label: 'monthly subscription fee' }, { value: MIN_TOPUP_LABEL_EN, label: 'minimum wallet top-up' }] },
  },
  steps: {
    fa: {
      items: [
        { title: 'حساب بسازید', desc: 'با ایمیل ثبت‌نام کنید. ساخت حساب رایگان است و هیچ کارت اعتباری‌ای لازم ندارد.' },
        { title: 'کیف پول را شارژ کنید', desc: `از ${MIN_TOPUP_LABEL_FA} به بالا، با کارت بانکی ایرانی.` },
        { title: 'وصل شوید یا شروع به چت کنید', desc: 'در مرورگر کار کنید، یا یک کلید API بسازید.' },
      ],
    },
    en: {
      items: [
        { title: 'Create an account', desc: 'Sign up with your email. Creating an account is free and needs no credit card.' },
        { title: 'Top up your wallet', desc: `From ${MIN_TOPUP_LABEL_EN} up, with an Iranian bank card.` },
        { title: 'Connect, or start chatting', desc: 'Work in the browser, or create an API key.' },
      ],
    },
  },
}
