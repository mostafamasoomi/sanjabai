import { dict } from '@/lib/i18n'
import { type IconName } from './ui/Icon'

/* ═══ Product tour — the launch-anytime, multi-step popup ════════════════════
   The static /guide page (app/guide) is a *dictionary*: one card per feature,
   each answering what/when/cost. This tour is the *teacher*: a multi-step
   modal, launchable from the top bar at any time, organised NOT feature by
   feature but around the workflows where features combine into real
   productivity — the thing the owner asked for ("تمرکز روی قسمت‌هایی که باهم
   به بهترین بهره‌وری می‌رسونن").

   Same product-contract rule as guide.strings.ts (docs/product-contract.md):
   NO asserted number — model count, speed, percentage, toman figure — is
   hardcoded below. Every cost sentence is qualitative and matches the billing
   code path already traced in guide.strings.ts's header (skills/memory/combos
   free to build, billed only at chat time; file attach + chat billed as normal
   token usage; scheduled task billed exactly like the manual run). The
   productTour.test.ts guard scans this file's runtime copy for any digit and
   fails on one, and checks every ctaHref resolves to a real route. */

export type TourStepId =
  | 'welcome'
  | 'assistants'
  | 'skills'
  | 'memory'
  | 'combos'
  | 'smart'
  | 'file'
  | 'tasks'
  | 'explore'

/** Fixed order. Chapters group consecutive steps; the modal shows the chapter
 *  label above each step and one progress dot per step. */
export const TOUR_STEP_ORDER: readonly TourStepId[] = [
  'welcome',
  'assistants',
  'skills',
  'memory',
  'combos',
  'smart',
  'file',
  'tasks',
  'explore',
]

export type TourStep = {
  /** Chapter label shown above the step title; steps sharing a label form a chapter. */
  chapter: string
  icon: IconName
  title: string
  body: string
  /** The workflow this chapter teaches, e.g. "دستیار + مهارت + حافظه". Optional. */
  combo?: string
  /** Call-to-action label + a REAL route under frontend/app/. Both optional
   *  (the welcome step has none). productTour.test.ts asserts ctaHref exists. */
  ctaLabel?: string
  ctaHref?: string
}

const FA = {
  launch: 'راهنمای تعاملی',
  launchTitle: 'راهنمای تعاملی سنجاب‌ای',
  dialogLabel: 'راهنمای تعاملی سنجاب‌ای',
  stepOf: (a: string, b: string) => `${a} از ${b}`,
  prev: 'قبلی',
  next: 'بعدی',
  finish: 'تمام',
  skip: 'رد کردن',
  close: 'بستن',
  guideCta: 'شروع راهنمای تعاملی',
  steps: {
    welcome: {
      chapter: 'شروع',
      icon: 'sparkles',
      title: 'به سنجاب‌ای خوش آمدی',
      body: 'این راهنمای کوتاه نشان می‌دهد قابلیت‌های سنجاب‌ای را چطور کنار هم بگذاری تا با کمترین زحمت بیشترین نتیجه را بگیری. هر وقت خواستی، از دکمهٔ راهنما بالای صفحه دوباره بازش کن.',
    },
    assistants: {
      chapter: 'متخصص شخصی‌ات را بساز',
      icon: 'sparkles',
      combo: 'دستیار + مهارت + حافظه',
      title: 'دستیار: یک نقش ثابت بساز',
      body: 'دستیار یک شخصیت و دستورِ ثابت است که هر گفتگوی تازه با همان شروع می‌شود — مثلاً «ویراستار فارسی» یا «مشاور کد». یک‌بار می‌سازی، همیشه همان لحن و زمینه را داری. ساختنش رایگان است و گفتگو با آن مثل هر گفتگوی دیگر حساب می‌شود.',
      ctaLabel: 'رفتن به دستیارها',
      ctaHref: '/assistants',
    },
    skills: {
      chapter: 'متخصص شخصی‌ات را بساز',
      icon: 'cpu',
      combo: 'دستیار + مهارت + حافظه',
      title: 'مهارت: کارِ تکراری را یک‌دکمه کن',
      body: 'مهارت الگوی آماده‌ای از پرامپت است؛ می‌توانی یک‌بار اجرایش کنی یا «فعال» نگهش داری تا روی همهٔ پیام‌های بعدی خودکار اعمال شود. مهارتِ فعال به هر پیام اضافه می‌شود، پس هزینه‌اش در هر پیام دوباره حساب می‌شود، نه فقط یک‌بار.',
      ctaLabel: 'رفتن به مهارت‌ها',
      ctaHref: '/skills',
    },
    memory: {
      chapter: 'متخصص شخصی‌ات را بساز',
      icon: 'clock',
      combo: 'دستیار + مهارت + حافظه',
      title: 'حافظه: خودش تو را می‌شناسد',
      body: 'سنجاب‌ای خودکار نکات مهمِ گفتگوها را نگه می‌دارد تا لازم نباشد هر بار خودت را از نو معرفی کنی. ساختِ این حافظه رایگان است؛ فقط وقتی در گفتگویی تازه استفاده شود مثل هر پیام عادی حساب می‌شود. این سه با هم — دستیار نقش، مهارت کار، حافظه شناختِ تو — یک متخصص می‌سازند که دقیقاً برای تو کوک شده.',
      ctaLabel: 'رفتن به حافظه',
      ctaHref: '/memory',
    },
    combos: {
      chapter: 'هرگز شکست نخور، همیشه ارزان',
      icon: 'compare',
      combo: 'ترکیب مدل + حالت هوشمند',
      title: 'ترکیب مدل: اگر یکی خطا داد، بعدی جواب می‌دهد',
      body: 'ترکیب، فهرستی مرتب از چند مدل است؛ اگر مدل اول در دسترس نباشد یا خطا بدهد، درخواست به‌جای شکست به مدل بعدیِ همان فهرست می‌رود. یک مدل سریع و ارزان را با یک پشتیبانِ دقیق‌تر کنار هم بگذار تا درخواست همیشه جواب بگیرد. ساختن و ویرایش ترکیب رایگان است؛ فقط مدلی که واقعاً پاسخ می‌دهد به قیمت خودش حساب می‌شود.',
      ctaLabel: 'رفتن به ترکیب‌ها',
      ctaHref: '/combos',
    },
    smart: {
      chapter: 'هرگز شکست نخور، همیشه ارزان',
      icon: 'sparkles',
      combo: 'ترکیب مدل + حالت هوشمند',
      title: 'حالت هوشمند: انتخاب مدل را بسپار',
      body: 'در گفتگو، حالت هوشمند به‌جای تو مدلِ مناسبِ هر پیام را انتخاب می‌کند. بعضی گزینه‌هایش (مثل مسیریاب هوشمند) هزینه‌ای جدا از خودِ مدل دارند و پیش از استفاده صادقانه می‌گویند. کنار ترکیب مدل، یعنی هم انتخاب درست، هم پشتیبانِ همیشه‌آماده.',
      ctaLabel: 'رفتن به گفتگو',
      ctaHref: '/chat',
    },
    file: {
      chapter: 'از سند خودت بپرس',
      icon: 'file',
      title: 'پرسش از فایل: پاسخ از متنِ خودت',
      body: 'می‌توانی یک فایل را به پیام در گفتگو پیوست کنی تا پاسخ از روی همان سند داده شود، نه فقط دانش عمومی مدل — مثلاً یک قرارداد یا گزارش. هم پردازش فایل و هم گفتگویی که از آن استفاده می‌کند، مثل مصرف عادی توکن از کیف پول کم می‌شود.',
      ctaLabel: 'رفتن به گفتگو',
      ctaHref: '/chat',
    },
    tasks: {
      chapter: 'کارها را خودکار کن',
      icon: 'calendar',
      title: 'تسک زمان‌بندی‌شده: بدون تو اجرا می‌شود',
      body: 'وظیفه‌ای که یک پرامپت مشخص را طبق زمان‌بندی، بدون اینکه خودت هر بار اجرایش کنی، خودکار اجرا می‌کند — مثل خلاصهٔ روزانه یا یادآوری دوره‌ای. هر بار که اجرا می‌شود، دقیقاً مثل اجرای دستیِ همان پرامپت حساب می‌شود.',
      ctaLabel: 'رفتن به تسک‌ها',
      ctaHref: '/tasks',
    },
    explore: {
      chapter: 'حالا کاوش کن',
      icon: 'models',
      title: 'کجا چه چیزی هست',
      body: 'در «مدل‌ها» می‌بینی چه مدل‌هایی زنده‌اند و کدام به کارت می‌آید؛ در «مقایسه» یک پرسش را هم‌زمان به چند مدل می‌دهی؛ «کیف پول» و «مصرف» خرجت را شفاف نشان می‌دهند. هر وقت خواستی همین راهنما را از دکمهٔ راهنما بالای صفحه باز کن.',
      ctaLabel: 'دیدن مدل‌ها',
      ctaHref: '/models',
    },
  } as Record<TourStepId, TourStep>,
}

const EN: typeof FA = {
  launch: 'Interactive guide',
  launchTitle: 'Sanjabai interactive guide',
  dialogLabel: 'Sanjabai interactive guide',
  stepOf: (a: string, b: string) => `${a} of ${b}`,
  prev: 'Back',
  next: 'Next',
  finish: 'Done',
  skip: 'Skip',
  close: 'Close',
  guideCta: 'Start the interactive guide',
  steps: {
    welcome: {
      chapter: 'Start',
      icon: 'sparkles',
      title: 'Welcome to Sanjabai',
      body: 'This short guide shows how to combine Sanjabai\'s features so you get the most out of the least effort. Reopen it any time from the help button in the top bar.',
    },
    assistants: {
      chapter: 'Build your personal expert',
      icon: 'sparkles',
      combo: 'Assistant + Skill + Memory',
      title: 'Assistant: set a fixed role',
      body: 'An assistant is a preset persona and a fixed instruction every new conversation starts from — an editor, a coding advisor. Build it once, and always get the same tone and context. Creating one is free, and chatting with it is billed like any other conversation.',
      ctaLabel: 'Go to Assistants',
      ctaHref: '/assistants',
    },
    skills: {
      chapter: 'Build your personal expert',
      icon: 'cpu',
      combo: 'Assistant + Skill + Memory',
      title: 'Skill: turn a repeated task into one button',
      body: 'A skill is a ready-made prompt template you can run once or keep active so it applies to every future message automatically. An active skill is added to every message, so its cost is charged again on each message, not just once.',
      ctaLabel: 'Go to Skills',
      ctaHref: '/skills',
    },
    memory: {
      chapter: 'Build your personal expert',
      icon: 'clock',
      combo: 'Assistant + Skill + Memory',
      title: 'Memory: it already knows you',
      body: 'Sanjabai automatically keeps the important facts from your conversations so you don\'t re-introduce yourself every time. Building this memory is free; only using it in a new conversation is billed like any other message. Together — assistant for the role, skill for the task, memory for knowing you — the three make an expert tuned exactly to you.',
      ctaLabel: 'Go to Memory',
      ctaHref: '/memory',
    },
    combos: {
      chapter: 'Never fail, always cheap',
      icon: 'compare',
      combo: 'Model combo + Smart mode',
      title: 'Model combo: if one errors, the next answers',
      body: 'A combo is an ordered list of models; if the first is unavailable or errors out, the request moves to the next in the same list instead of failing. Pair a fast, cheap model with a more capable backup so a request always gets answered. Building and editing a combo is free; only the model that actually answers is billed, at its own price.',
      ctaLabel: 'Go to Combos',
      ctaHref: '/combos',
    },
    smart: {
      chapter: 'Never fail, always cheap',
      icon: 'sparkles',
      combo: 'Model combo + Smart mode',
      title: 'Smart mode: hand off model choice',
      body: 'In chat, smart mode picks the right model for each message on your behalf. Some of its options (like the smart router) cost extra on top of the model itself, and say so honestly before you use them. Alongside a combo, that\'s the right pick plus an always-ready backup.',
      ctaLabel: 'Go to Chat',
      ctaHref: '/chat',
    },
    file: {
      chapter: 'Ask your own document',
      icon: 'file',
      title: 'Ask from a file: answers from your own text',
      body: 'Attach a file to a message in chat so the answer comes from that document instead of only the model\'s general knowledge — a contract, a report. Both processing the file and the conversation that uses it are billed like normal token usage from your wallet.',
      ctaLabel: 'Go to Chat',
      ctaHref: '/chat',
    },
    tasks: {
      chapter: 'Automate the work',
      icon: 'calendar',
      title: 'Scheduled task: runs without you',
      body: 'A task runs a specific prompt on a schedule without you triggering it — a daily summary, a periodic reminder. Every run is billed exactly like running that same prompt manually.',
      ctaLabel: 'Go to Tasks',
      ctaHref: '/tasks',
    },
    explore: {
      chapter: 'Now explore',
      icon: 'models',
      title: 'Where everything lives',
      body: '"Models" shows which models are live and which suit you; "Compare" sends one question to several models at once; "Wallet" and "Usage" show your spending transparently. Reopen this guide any time from the help button in the top bar.',
      ctaLabel: 'See Models',
      ctaHref: '/models',
    },
  },
}

export const productTourStrings = dict(FA, EN)
