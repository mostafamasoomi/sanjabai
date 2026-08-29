import { dict } from '@/lib/i18n'
import type { TemplateId, TourTemplate } from './templates'

export type { TemplateId, TemplateTheme, TourTemplate, TemplateApply } from './templates'
export { TEMPLATE_ORDER, templateApplyHref } from './templates'

/* ═══ Template gallery copy — bilingual, one file per the repo's `.strings.ts`
   convention (ProductTour.strings.ts, guide.strings.ts: FA + EN + dict() all
   in one file, never split by language — productI18nCoverage.test.ts's
   per-file `EN: typeof FA` + `dict()` guard assumes exactly this shape).

   Same product-contract rule as those two files: NO digit sequence anywhere
   in this file's copy, including inside chat prompts (templates.test.ts
   scans every field, prompts included). Voice matches ProductTour: warm,
   concrete, second person. `Record<TemplateId, TourTemplate>` (not a bare
   object literal) is the completeness check for FA -- a missing id, or a
   value that doesn't match TourTemplate's shape, is a compile error; `EN:
   typeof FA` then makes a missing/mistyped EN entry a compile error too. */

const FA: Record<TemplateId, TourTemplate> = {
  'fa-editor': {
    id: 'fa-editor',
    theme: 'expert',
    icon: 'sparkles',
    combo: 'دستیار + مهارت + حافظه',
    title: 'ویراستار فارسی همیشگی',
    tagline: 'دستیاری که هر متن را با همان لحن ثابت ویرایش می‌کند.',
    ingredients: [
      'یک دستیار تازه بساز و نقشش را «ویراستار فارسی» بگذار.',
      'در دستور ثابتش بنویس چه لحنی می‌خواهی — رسمی، صمیمی یا خنثی.',
      'هر بار متنی برایش می‌فرستی، همان لحن رعایت می‌شود، بدون توضیح دوباره.',
    ],
    apply: { kind: 'navigate', href: '/assistants/new' },
    applyLabel: 'ساخت این دستیار',
  },
  'code-advisor': {
    id: 'code-advisor',
    theme: 'expert',
    icon: 'code',
    combo: 'دستیار + مهارت + حافظه',
    title: 'مشاور کدنویسی پروژه‌محور',
    tagline: 'دستیاری که پروژه‌ات را از حافظه می‌شناسد و با همان زمینه پیشنهاد می‌دهد.',
    ingredients: [
      'یک دستیار با نقش «مشاور کد» بساز و زبان و چارچوب پروژه‌ات را در دستور ثابتش بنویس.',
      'همان‌طور که با آن گفتگو می‌کنی، نکات مهم پروژه در حافظه ذخیره می‌شود.',
      'در گفتگوهای بعدی دیگر لازم نیست دوباره زمینهٔ پروژه را توضیح بدهی.',
    ],
    apply: { kind: 'navigate', href: '/assistants/new' },
    applyLabel: 'ساخت این دستیار',
  },
  'tone-translator': {
    id: 'tone-translator',
    theme: 'expert',
    icon: 'globe',
    combo: 'مهارت',
    title: 'مترجم لحن‌نگه‌دار',
    tagline: 'ترجمه‌ای که سبک نویسنده را حفظ می‌کند، آماده به‌عنوان یک مهارت.',
    ingredients: [
      'یک مهارت تازه بساز و در متن آن بخواه لحن و سبک نویسنده در ترجمه حفظ شود.',
      'زبان مقصد را در همان الگو مشخص کن تا هر بار دوباره ننویسی.',
      'هر متنی به این مهارت بدهی، با همان سبک اصلی نویسنده ترجمه می‌شود.',
    ],
    apply: { kind: 'navigate', href: '/skills' },
    applyLabel: 'ساخت این مهارت',
  },
  'contract-analyzer': {
    id: 'contract-analyzer',
    theme: 'document',
    icon: 'file',
    combo: 'پیوست فایل + گفتگو',
    title: 'تحلیل‌گر قرارداد',
    tagline: 'بندهای مهم و ریسک‌های قرارداد پیوست‌شده را بیرون می‌کشد.',
    ingredients: [
      'فایل قرارداد را با دکمهٔ پیوست به پیام گفتگو اضافه کن.',
      'این پرامپت آماده را بفرست تا بندهای مهم و ریسک‌ها را برایت جدا کند.',
    ],
    apply: {
      kind: 'chat-prefill',
      prompt: 'بندهای مهم و ریسک‌های این قرارداد پیوست‌شده را فهرست کن و برای هر بند توضیح بده چرا اهمیت دارد.',
    },
    applyLabel: 'شروع در گفتگو',
  },
  'report-summarizer': {
    id: 'report-summarizer',
    theme: 'document',
    icon: 'chart',
    combo: 'پیوست فایل + گفتگو',
    title: 'خلاصه‌ساز گزارش بلند',
    tagline: 'گزارش چندصفحه‌ای را به خلاصهٔ مدیریتی تبدیل می‌کند.',
    ingredients: [
      'فایل گزارش را با دکمهٔ پیوست به پیام گفتگو اضافه کن.',
      'این پرامپت آماده را بفرست تا خلاصهٔ مدیریتی و نکات کلیدی را بگیری.',
    ],
    apply: {
      kind: 'chat-prefill',
      prompt: 'از فایل پیوست‌شده یک خلاصهٔ مدیریتی کوتاه بنویس و نکات کلیدی را جداگانه فهرست کن.',
    },
    applyLabel: 'شروع در گفتگو',
  },
  'meeting-decisions': {
    id: 'meeting-decisions',
    theme: 'document',
    icon: 'check',
    combo: 'پیوست فایل + گفتگو',
    title: 'استخراج تصمیم‌های جلسه',
    tagline: 'از متن جلسه، تصمیم‌ها و کارهای بعدی را جدا از هم بیرون می‌کشد.',
    ingredients: [
      'متن یا فایل صورت‌جلسه را به پیام گفتگو پیوست یا کپی کن.',
      'این پرامپت آماده را بفرست تا تصمیم‌ها و کارهای بعدی هرکس جدا فهرست شوند.',
    ],
    apply: {
      kind: 'chat-prefill',
      prompt: 'از متن این جلسه، تصمیم‌های گرفته‌شده و کارهای بعدی هرکس را جدا از هم و به‌صورت فهرست بنویس.',
    },
    applyLabel: 'شروع در گفتگو',
  },
  'daily-summary': {
    id: 'daily-summary',
    theme: 'automation',
    icon: 'calendar',
    combo: 'تسک زمان‌بندی‌شده',
    title: 'خلاصهٔ روزانهٔ کاری',
    tagline: 'هر روز یک جمع‌بندی آماده، بدون اینکه خودت هر بار درخواستش کنی.',
    ingredients: [
      'یک تسک تازه بساز و پرامپتش را «جمع‌بندی کارهای امروز» بگذار.',
      'زمان‌بندی روزانه را انتخاب کن تا هر روز خودکار اجرا شود.',
    ],
    apply: { kind: 'navigate', href: '/tasks' },
    applyLabel: 'ساخت این تسک',
  },
  'weekly-review': {
    id: 'weekly-review',
    theme: 'automation',
    icon: 'clock',
    combo: 'تسک زمان‌بندی‌شده',
    title: 'مرور هفتگی اهداف',
    tagline: 'هر هفته پیشرفتت را با کمک حافظه مرور می‌کند.',
    ingredients: [
      'یک تسک تازه بساز و پرامپتش را دربارهٔ مرور اهداف هفته بنویس.',
      'زمان‌بندی هفتگی را انتخاب کن تا خودکار در همان روز اجرا شود.',
    ],
    apply: { kind: 'navigate', href: '/tasks' },
    applyLabel: 'ساخت این تسک',
  },
  'customer-followup': {
    id: 'customer-followup',
    theme: 'automation',
    icon: 'bell',
    combo: 'تسک زمان‌بندی‌شده',
    title: 'یادآور پیگیری مشتری',
    tagline: 'پیام پیگیری دوره‌ای مشتری را از پیش آماده می‌کند.',
    ingredients: [
      'یک تسک تازه بساز و پرامپتش را برای نوشتن پیام پیگیری مشتری تنظیم کن.',
      'زمان‌بندی دوره‌ای دلخواه را انتخاب کن تا هر بار خودکار آماده شود.',
    ],
    apply: { kind: 'navigate', href: '/tasks' },
    applyLabel: 'ساخت این تسک',
  },
  'combo-backup': {
    id: 'combo-backup',
    theme: 'reliability',
    icon: 'compare',
    combo: 'ترکیب مدل',
    title: 'ترکیب ارزان + پشتیبان قوی',
    tagline: 'مدل سریع جواب می‌دهد؛ اگر خطا داد، پشتیبان دقیق‌تر خودش وارد می‌شود.',
    ingredients: [
      'یک ترکیب تازه بساز و مدل سریع و ارزان را اول فهرست بگذار.',
      'یک مدل دقیق‌تر را به‌عنوان پشتیبان دوم اضافه کن تا اگر اولی خطا داد، درخواست به آن برود.',
    ],
    apply: { kind: 'navigate', href: '/combos' },
    applyLabel: 'ساخت این ترکیب',
  },
  'smart-mode-everyday': {
    id: 'smart-mode-everyday',
    theme: 'reliability',
    icon: 'sparkles',
    combo: 'ترکیب مدل + حالت هوشمند',
    title: 'حالت هوشمند برای کار روزمره',
    tagline: 'انتخاب مدل هر پیام را بسپار، هزینه بهینه بماند.',
    ingredients: [
      'در گفتگو، حالت هوشمند را از نوار پیام روشن کن.',
      'این پرامپت آماده را بفرست تا ببینی مدل مناسب هر پیام خودش انتخاب می‌شود.',
    ],
    apply: {
      kind: 'chat-prefill',
      smartHint: true,
      prompt: 'برایم یک پیام کاری روزمره بنویس؛ می‌خواهم ببینم حالت هوشمند چه مدلی برایش انتخاب می‌کند.',
    },
    applyLabel: 'شروع در گفتگو',
  },
  'compare-first': {
    id: 'compare-first',
    theme: 'reliability',
    icon: 'compare',
    combo: 'مقایسهٔ مدل‌ها',
    title: 'اول مقایسه بعد انتخاب',
    tagline: 'یک پرسش را هم‌زمان به چند مدل بده و پاسخ‌ها را کنار هم ببین.',
    ingredients: [
      'پرسش موردنظرت را در صفحهٔ مقایسه بنویس.',
      'چند مدل را هم‌زمان انتخاب کن تا پاسخ‌هایشان را کنار هم ببینی.',
    ],
    apply: { kind: 'navigate', href: '/compare' },
    applyLabel: 'شروع مقایسه',
  },
  'formal-email': {
    id: 'formal-email',
    theme: 'everyday',
    icon: 'mail',
    combo: 'گفتگو + پرامپت آماده',
    title: 'ایمیل رسمی از چند خط یادداشت',
    tagline: 'یادداشت پراکنده را به یک ایمیل رسمی و مرتب تبدیل می‌کند.',
    ingredients: [
      'یادداشت‌های پراکنده‌ات را در جای مشخص‌شدهٔ پرامپت آماده بگذار.',
      'این پرامپت را بفرست تا از آن‌ها یک ایمیل رسمی و مرتب بسازی.',
    ],
    apply: {
      kind: 'chat-prefill',
      prompt: 'از این یادداشت‌های پراکنده یک ایمیل رسمی، مرتب و مؤدبانه بنویس: [یادداشت‌هایت را اینجا بگذار]',
    },
    applyLabel: 'شروع در گفتگو',
  },
  'idea-to-post': {
    id: 'idea-to-post',
    theme: 'everyday',
    icon: 'rocket',
    combo: 'گفتگو + پرامپت آماده',
    title: 'از ایده تا پست شبکهٔ اجتماعی',
    tagline: 'یک ایده را به چند نسخهٔ آمادهٔ پست تبدیل می‌کند.',
    ingredients: [
      'ایده‌ات را در جای مشخص‌شدهٔ پرامپت آماده بگذار.',
      'این پرامپت را بفرست تا چند نسخهٔ متفاوت از پست آماده بگیری.',
    ],
    apply: {
      kind: 'chat-prefill',
      prompt: 'از این ایده چند نسخهٔ متفاوت پست برای شبکهٔ اجتماعی بنویس، هرکدام با لحنی متفاوت: [ایده‌ات را اینجا بگذار]',
    },
    applyLabel: 'شروع در گفتگو',
  },
}

const EN: typeof FA = {
  'fa-editor': {
    id: 'fa-editor',
    theme: 'expert',
    icon: 'sparkles',
    combo: 'Assistant + Skill + Memory',
    title: 'A permanent Persian editor',
    tagline: 'An assistant that edits every text with the same fixed tone.',
    ingredients: [
      'Create a new assistant and set its role to "Persian editor".',
      'In its fixed instruction, write which tone you want — formal, casual, or neutral.',
      'Every text you send it keeps that tone, without re-explaining it each time.',
    ],
    apply: { kind: 'navigate', href: '/assistants/new' },
    applyLabel: 'Build this assistant',
  },
  'code-advisor': {
    id: 'code-advisor',
    theme: 'expert',
    icon: 'code',
    combo: 'Assistant + Skill + Memory',
    title: 'A project-aware coding advisor',
    tagline: 'An assistant that knows your project from memory and answers with that context.',
    ingredients: [
      'Create an assistant with the role "coding advisor" and write your project\'s language and framework into its fixed instruction.',
      'As you chat with it, the important facts about your project get saved to memory.',
      'In later conversations you no longer need to re-explain the project context.',
    ],
    apply: { kind: 'navigate', href: '/assistants/new' },
    applyLabel: 'Build this assistant',
  },
  'tone-translator': {
    id: 'tone-translator',
    theme: 'expert',
    icon: 'globe',
    combo: 'Skill',
    title: 'A tone-preserving translator',
    tagline: 'Translation that keeps the writer\'s own style, ready as a skill.',
    ingredients: [
      'Create a new skill and ask it to preserve the writer\'s tone and style while translating.',
      'Set the target language in the same template so you never re-type it.',
      'Any text you give this skill comes back translated in the original author\'s style.',
    ],
    apply: { kind: 'navigate', href: '/skills' },
    applyLabel: 'Build this skill',
  },
  'contract-analyzer': {
    id: 'contract-analyzer',
    theme: 'document',
    icon: 'file',
    combo: 'File attach + Chat',
    title: 'A contract analyzer',
    tagline: 'Pulls out the important clauses and risks from an attached contract.',
    ingredients: [
      'Attach the contract file to a chat message using the attach button.',
      'Send this ready-made prompt to have it separate the important clauses and risks.',
    ],
    apply: {
      kind: 'chat-prefill',
      prompt: 'List the important clauses and risks in this attached contract, and explain why each one matters.',
    },
    applyLabel: 'Start in chat',
  },
  'report-summarizer': {
    id: 'report-summarizer',
    theme: 'document',
    icon: 'chart',
    combo: 'File attach + Chat',
    title: 'A long-report summarizer',
    tagline: 'Turns a multi-page report into an executive summary.',
    ingredients: [
      'Attach the report file to a chat message using the attach button.',
      'Send this ready-made prompt to get an executive summary and the key points.',
    ],
    apply: {
      kind: 'chat-prefill',
      prompt: 'Write a short executive summary of the attached file and list the key points separately.',
    },
    applyLabel: 'Start in chat',
  },
  'meeting-decisions': {
    id: 'meeting-decisions',
    theme: 'document',
    icon: 'check',
    combo: 'File attach + Chat',
    title: 'Meeting decision extractor',
    tagline: 'Separates decisions from follow-up work in meeting notes.',
    ingredients: [
      'Attach or paste the meeting notes into a chat message.',
      'Send this ready-made prompt to get decisions and each person\'s follow-up work listed separately.',
    ],
    apply: {
      kind: 'chat-prefill',
      prompt: 'From this meeting text, write the decisions that were made and everyone\'s follow-up work as two separate lists.',
    },
    applyLabel: 'Start in chat',
  },
  'daily-summary': {
    id: 'daily-summary',
    theme: 'automation',
    icon: 'calendar',
    combo: 'Scheduled task',
    title: 'A daily work summary',
    tagline: 'A ready recap every day, without you asking for it each time.',
    ingredients: [
      'Create a new task and set its prompt to "summarize today\'s work".',
      'Pick a daily schedule so it runs automatically every day.',
    ],
    apply: { kind: 'navigate', href: '/tasks' },
    applyLabel: 'Build this task',
  },
  'weekly-review': {
    id: 'weekly-review',
    theme: 'automation',
    icon: 'clock',
    combo: 'Scheduled task',
    title: 'A weekly goal review',
    tagline: 'Reviews your progress every week with the help of memory.',
    ingredients: [
      'Create a new task and write its prompt around reviewing your weekly goals.',
      'Pick a weekly schedule so it runs automatically on that day.',
    ],
    apply: { kind: 'navigate', href: '/tasks' },
    applyLabel: 'Build this task',
  },
  'customer-followup': {
    id: 'customer-followup',
    theme: 'automation',
    icon: 'bell',
    combo: 'Scheduled task',
    title: 'A customer follow-up reminder',
    tagline: 'Prepares a recurring customer follow-up message in advance.',
    ingredients: [
      'Create a new task and set its prompt to draft a customer follow-up message.',
      'Pick whatever recurring schedule fits so it\'s ready automatically each time.',
    ],
    apply: { kind: 'navigate', href: '/tasks' },
    applyLabel: 'Build this task',
  },
  'combo-backup': {
    id: 'combo-backup',
    theme: 'reliability',
    icon: 'compare',
    combo: 'Model combo',
    title: 'Cheap primary + strong backup',
    tagline: 'The fast model answers; if it errors, a more capable backup steps in.',
    ingredients: [
      'Create a new combo and list a fast, cheap model first.',
      'Add a more capable model as the second, backup entry so the request moves to it if the first errors.',
    ],
    apply: { kind: 'navigate', href: '/combos' },
    applyLabel: 'Build this combo',
  },
  'smart-mode-everyday': {
    id: 'smart-mode-everyday',
    theme: 'reliability',
    icon: 'sparkles',
    combo: 'Model combo + Smart mode',
    title: 'Smart mode for everyday work',
    tagline: 'Hand off the model choice for each message and keep cost efficient.',
    ingredients: [
      'In chat, turn smart mode on from the message bar.',
      'Send this ready-made prompt to see the right model get picked for it automatically.',
    ],
    apply: {
      kind: 'chat-prefill',
      smartHint: true,
      prompt: 'Write me an everyday work message; I want to see which model smart mode picks for it.',
    },
    applyLabel: 'Start in chat',
  },
  'compare-first': {
    id: 'compare-first',
    theme: 'reliability',
    icon: 'compare',
    combo: 'Model comparison',
    title: 'Compare first, then pick',
    tagline: 'Send one question to several models at once and see the answers side by side.',
    ingredients: [
      'Write your question on the compare page.',
      'Select several models at once to see their answers side by side.',
    ],
    apply: { kind: 'navigate', href: '/compare' },
    applyLabel: 'Start comparing',
  },
  'formal-email': {
    id: 'formal-email',
    theme: 'everyday',
    icon: 'mail',
    combo: 'Chat + Ready prompt',
    title: 'A formal email from scattered notes',
    tagline: 'Turns scattered notes into one tidy, formal email.',
    ingredients: [
      'Drop your scattered notes into the marked spot in the ready-made prompt.',
      'Send it to turn them into a tidy, formal email.',
    ],
    apply: {
      kind: 'chat-prefill',
      prompt: 'Write a formal, tidy, polite email from these scattered notes: [put your notes here]',
    },
    applyLabel: 'Start in chat',
  },
  'idea-to-post': {
    id: 'idea-to-post',
    theme: 'everyday',
    icon: 'rocket',
    combo: 'Chat + Ready prompt',
    title: 'From idea to social post',
    tagline: 'Turns one idea into several ready post drafts.',
    ingredients: [
      'Drop your idea into the marked spot in the ready-made prompt.',
      'Send it to get several different post drafts ready.',
    ],
    apply: {
      kind: 'chat-prefill',
      prompt: 'Write several different social media post drafts from this idea, each in a different tone: [put your idea here]',
    },
    applyLabel: 'Start in chat',
  },
}

/** `templateStrings(lang)[id]` -> the full `TourTemplate` for that language. */
export const templateStrings = dict(FA, EN)

/* Gallery CHROME (heading/subheading/toggle label/smart-mode hint) — kept as
 * its own small dict rather than literals inside TemplateGallery.tsx, per
 * productI18nCoverage.test.ts: a component file may not hold a raw Persian
 * string, only a dictionary file may. */
const GALLERY_FA = {
  heading: 'الگوهای آماده',
  subheading: 'چهارده دستور شروع سریع — هرکدام چند قابلیت را کنار هم می‌گذارد تا با کمترین کار بیشترین نتیجه را بگیری.',
  ingredientsToggle: 'مراحل ساخت',
  smartHint: 'پیش از فرستادن، حالت هوشمند را از نوار پیام روشن کن.',
}
const GALLERY_EN: typeof GALLERY_FA = {
  heading: 'Ready-made templates',
  subheading: 'Fourteen quick-start recipes — each combines several features so you get the most from the least effort.',
  ingredientsToggle: 'Steps',
  smartHint: 'Turn smart mode on from the message bar before sending.',
}
export const templateGalleryStrings = dict(GALLERY_FA, GALLERY_EN)
