import { dict } from '@/lib/i18n'

/* ═══ The in-product education surface (P-GUIDE, phase 8 پ-۴) ═══════════════
   One dictionary, two consumers: guide/page.tsx renders `sections` as the six
   static cards on /guide, and components/Hint.tsx renders `hints` as inline
   popovers wired into OTHER pages by the senior (this packet only builds and
   exports the component, see Hint.tsx's own header).

   Product-contract rule (non-negotiable, see docs/product-contract.md): no
   asserted number -- model count, speed, percentage, toman figure -- is
   hardcoded below. Every "cost" answer is qualitative and was checked against
   the actual billing code path before being written (see the file-by-file
   trace in the P-GUIDE handoff report), not guessed:
     - skills.py's /skills/{id}/use only renders a prompt string and bumps a
       counter -- zero billing calls. The chat turn that follows is billed
       normally, at the picked model's price.
     - services/memory_extractor.py's extract_memories() has zero reserve/
       bill calls -- automatic extraction is not charged; only the chat turn
       that later uses a saved memory is billed as usual.
     - combos.py (CRUD for /me/combos) has zero billing calls -- a combo only
       costs money at chat time, whichever model in the list actually answers.
     - services/rag.py and services/embeddings.py DO bill (reserve/settle
       around both the embedding call and the query) -- reflected in the
       "rag" section's cost line.
     - task_execution.py's scheduled-task run is the same reserve -> upstream
       -> settle -> release bracket as a manual chat call (tasks.py:250-ish).

   "rag" section naming note: rag_endpoints.py's /v1/rag/upload+query (real
   chunking/embedding/pgvector retrieval) has ZERO frontend consumer as of
   this packet -- grepped, confirmed. The only real, shipped, honestly-
   labelled surface that answers from a document today is the per-message
   file attach in /chat (chat_web.py's /v1/chat/with-file: plain text
   extraction + context injection, NOT vector retrieval). This section is
   worded around THAT feature, never claiming a persistent document library
   that doesn't exist in the UI. Flagged to the senior as a product gap --
   see the handoff report's "Decision/contract" section. */

export type GuideSectionKey = 'skills' | 'memory' | 'combos' | 'assistants' | 'rag' | 'tasks'

/** Fixed order per the P-GUIDE packet: skills, memory, combos, assistants, rag, tasks. */
export const GUIDE_SECTION_ORDER: readonly GuideSectionKey[] = ['skills', 'memory', 'combos', 'assistants', 'rag', 'tasks']

export type GuideSection = {
  title: string
  what: string
  when: string
  cost: string
  startLabel: string
  /** A real path under frontend/app/ -- guideContent.test.ts asserts this. */
  startHref: string
}

/** 6 hint ids, one per packet-named placement (skill activation, the
 *  «استفاده» button, model combos, smart mode, automatic memory, autonomy).
 *  Wiring these into the named files is the senior's call -- see the handoff
 *  report for the exact file:line recommendation per id. */
export type GuideHintId =
  | 'skills.activate'
  | 'skills.useButton'
  | 'combos.build'
  | 'chat.smartMode'
  | 'memory.auto'
  | 'profile.autonomy'

export const GUIDE_HINT_IDS: readonly GuideHintId[] = [
  'skills.activate',
  'skills.useButton',
  'combos.build',
  'chat.smartMode',
  'memory.auto',
  'profile.autonomy',
]

const FA = {
  pageTitle: 'راهنما',
  pageSubtitle: 'برای هر قابلیت می‌گوییم چیست، کِی به‌دردت می‌خورد و چقدر هزینه دارد.',
  questionLabels: {
    what: 'چیست؟',
    when: 'کِی به‌دردت می‌خورد؟',
    cost: 'هزینه‌اش چقدر است؟',
    start: 'کجا شروع کنی',
  },
  sections: {
    skills: {
      title: 'مهارت',
      what: 'مهارت الگوی آماده‌ای از پرامپت است که می‌توانی یک‌بار اجرا کنی یا با «فعال‌سازی» همیشه روی گفتگوهای بعدی روشن نگه داری.',
      when: 'وقتی کاری را مرتب تکرار می‌کنی — خلاصه‌سازی، ویرایش متن یا پاسخ با یک لحن ثابت — و نمی‌خواهی هر بار همان دستور را از نو بنویسی.',
      cost: 'دکمه «استفاده» فقط هزینه عادی گفتگو با مدل انتخابی را دارد. مهارتی که فعال نگه می‌داری به هر پیام اضافه می‌شود، پس هزینه‌اش در هر پیام دوباره حساب می‌شود، نه فقط یک‌بار.',
      startLabel: 'شروع از مارکتپلیس مهارت‌ها',
      startHref: '/skills',
    },
    memory: {
      title: 'حافظه',
      what: 'سیستم به‌صورت خودکار نکات مهم را از گفتگوها استخراج و ذخیره می‌کند تا در گفتگوهای بعدی پاسخ‌های شخصی‌تر بدهد.',
      when: 'وقتی نمی‌خواهی هر بار از نو زمینه و ترجیحات خودت را توضیح بدهی.',
      cost: 'استخراج خودکار حافظه چیزی از کیف پول کم نمی‌کند؛ فقط وقتی حافظه ذخیره‌شده در یک گفتگوی تازه استفاده می‌شود، هزینه همان گفتگو مثل همیشه حساب می‌شود.',
      startLabel: 'شروع از حافظه',
      startHref: '/memory',
    },
    combos: {
      title: 'ترکیب مدل',
      what: 'ترکیب فهرستی مرتب از چند مدل است؛ اگر مدل اول در دسترس نباشد یا خطا بدهد، مدل بعدی همان فهرست پاسخ می‌دهد.',
      when: 'وقتی می‌خواهی یک مدل سریع و ارزان را با یک مدل دقیق‌تر پشتیبان کنار هم بگذاری تا درخواست همیشه پاسخ بگیرد، نه فقط وقتی مدل اول کار می‌کند.',
      cost: 'ساختن و ویرایش ترکیب هزینه‌ای ندارد؛ فقط وقتی یکی از مدل‌های ترکیب واقعاً پاسخ می‌دهد، دقیقاً به قیمت همان مدل از کیف پول کم می‌شود.',
      startLabel: 'شروع از ترکیب‌های من',
      startHref: '/combos',
    },
    assistants: {
      title: 'دستیار',
      what: 'دستیار یک شخصیت و دستور ثابت است که از پیش آماده کرده‌ای و هر گفتگوی تازه با همان شروع می‌شود.',
      when: 'وقتی برای یک نقش خاص — مثلاً ویراستار متن یا مشاور کدنویسی — همیشه همان زمینه و لحن را می‌خواهی، بدون تکرار تنظیمات در هر گفتگو.',
      cost: 'ساختن دستیار هزینه‌ای ندارد؛ گفتگو با آن دقیقاً مثل هر گفتگوی دیگر بر اساس مدل انتخابی حساب می‌شود.',
      startLabel: 'شروع از دستیارها',
      startHref: '/assistants',
    },
    rag: {
      title: 'پرسش‌وپاسخ از روی فایل',
      what: 'می‌توانی یک فایل را به یک پیام در گفتگو پیوست کنی تا پاسخ بر اساس همان فایل داده شود، نه فقط از دانش عمومی مدل.',
      when: 'وقتی سوال مربوط به محتوای یک فایل مشخص است — مثلاً یک قرارداد یا گزارش — و می‌خواهی مدل دقیقاً از همان متن پاسخ بدهد.',
      cost: 'هم پردازش فایلی که پیوست می‌کنی و هم گفتگویی که از آن استفاده می‌کند، مثل مصرف توکن عادی از کیف پول کم می‌شود.',
      startLabel: 'شروع از گفتگو (دکمه پیوست فایل)',
      startHref: '/chat',
    },
    tasks: {
      title: 'تسک‌های زمان‌بندی‌شده',
      what: 'وظیفه‌ای است که یک پرامپت مشخص را طبق زمان‌بندی، بدون اینکه خودت هر بار آن را اجرا کنی، خودکار اجرا می‌کند.',
      when: 'برای کارهای تکراری مثل خلاصه‌نویسی روزانه یا یادآوری دوره‌ای که نمی‌خواهی خودت هر بار آن را اجرا کنی.',
      cost: 'هر بار که وظیفه اجرا می‌شود، دقیقاً مثل اجرای دستی همان پرامپت از کیف پول کم می‌شود.',
      startLabel: 'شروع از تسک‌های زمان‌بندی‌شده',
      startHref: '/tasks',
    },
  } satisfies Record<GuideSectionKey, GuideSection>,
  hints: {
    'skills.activate': 'فعال‌سازی یعنی این مهارت به همه پیام‌های گفتگوهای بعدی اضافه می‌شود، نه فقط یک‌بار؛ هزینه‌اش هم در هر پیام دوباره حساب می‌شود.',
    'skills.useButton': 'دکمه «استفاده» فقط همین یک‌بار مهارت را اجرا می‌کند؛ برای فعال‌ماندن دائمی، آن را از «مهارت‌های فعال» بالای صفحه روشن کن.',
    'combos.build': 'ترکیب فهرستی مرتب از چند مدل است. اگر مدل اول پاسخ ندهد، درخواست به‌جای شکست خوردن، به مدل بعدی همان فهرست می‌رود.',
    'chat.smartMode': 'حالت هوشمند به‌جای تو مدل مناسب را برای هر پیام انتخاب می‌کند. برخی از گزینه‌های آن (مثل مسیریاب هوشمند) هزینه‌ای اضافه، جدا از خود مدل، دارند.',
    'memory.auto': 'این حافظه خودکار است و از گفتگوهای تو ساخته می‌شود؛ ساختن آن هزینه‌ای از کیف پول کم نمی‌کند، فقط استفاده از آن در یک گفتگوی تازه مثل هر پیام دیگر حساب می‌شود.',
    'profile.autonomy': 'این سطح تعیین می‌کند دستیارها و تسک‌های زمان‌بندی‌شده چقدر بدون تایید تو اجازه دارند کاری را انجام دهند.',
  } satisfies Record<GuideHintId, string>,
  hintOpen: 'راهنما',
  hintButtonLabel: '؟',
}

const EN: typeof FA = {
  pageTitle: 'Guide',
  pageSubtitle: 'For every feature: what it is, when it\'s useful, and what it costs.',
  questionLabels: {
    what: 'What is it?',
    when: 'When is it useful?',
    cost: 'What does it cost?',
    start: 'Where to start',
  },
  sections: {
    skills: {
      title: 'Skills',
      what: 'A skill is a ready-made prompt template you can either run once or turn on permanently so it stays active on your future conversations.',
      when: 'For work you repeat often — summarizing, editing text, or answering in one consistent style — when you don\'t want to rewrite the same instruction every time.',
      cost: 'The "Use" button only costs the normal price of chatting with the model you picked. A skill you keep active is added to every message, so its cost is charged again on every message, not just once.',
      startLabel: 'Start from the skills marketplace',
      startHref: '/skills',
    },
    memory: {
      title: 'Memory',
      what: 'The system automatically extracts and saves important facts from your conversations so it can give more personalized answers in future chats.',
      when: 'When you don\'t want to explain your context and preferences from scratch every time.',
      cost: 'Automatic memory extraction doesn\'t charge your wallet; only when a saved memory is used in a new conversation is that conversation billed as usual.',
      startLabel: 'Start from Memory',
      startHref: '/memory',
    },
    combos: {
      title: 'Model combos',
      what: 'A combo is an ordered list of several models; if the first model is unavailable or errors out, the next model in the same list answers instead.',
      when: 'When you want to pair a fast, cheap model with a more capable backup model so a request always gets answered, not just when the first model happens to work.',
      cost: 'Building and editing a combo costs nothing; you\'re only charged when one of the combo\'s models actually answers, at exactly that model\'s price.',
      startLabel: 'Start from My combos',
      startHref: '/combos',
    },
    assistants: {
      title: 'Assistants',
      what: 'An assistant is a preset persona and a fixed instruction (system prompt) that every new conversation starts from.',
      when: 'When you always want the same context and tone for a specific role — an editor, a coding advisor — without repeating the setup in every conversation.',
      cost: 'Creating an assistant costs nothing; chatting with it is billed exactly like any other conversation, based on the model you chose.',
      startLabel: 'Start from Assistants',
      startHref: '/assistants',
    },
    rag: {
      title: 'Q&A from a file',
      what: 'You can attach a file to a message in chat so the answer is based on that file\'s content instead of only the model\'s general knowledge.',
      when: 'When your question is about a specific file — a contract, a report — and you want the model to answer strictly from that text.',
      cost: 'Both processing the attached file and the conversation that uses it are billed like normal token usage from your wallet.',
      startLabel: 'Start from Chat (the attach-file button)',
      startHref: '/chat',
    },
    tasks: {
      title: 'Scheduled tasks',
      what: 'A task runs a specific prompt automatically on a schedule, without you having to trigger it yourself every time.',
      when: 'For recurring work like a daily summary or a periodic reminder that you don\'t want to remember to run yourself.',
      cost: 'Every time a task runs, it\'s billed from your wallet exactly like running that same prompt manually.',
      startLabel: 'Start from Scheduled tasks',
      startHref: '/tasks',
    },
  },
  hints: {
    'skills.activate': 'Activating means this skill is added to every message in your future conversations, not just once — its cost is recalculated on every message too.',
    'skills.useButton': 'The "Use" button runs the skill just this one time. To keep it on permanently, turn it on from "Active skills" at the top of the page.',
    'combos.build': 'A combo is an ordered list of models. If the first model doesn\'t answer, the request moves to the next model in that same list instead of failing.',
    'chat.smartMode': 'Smart mode picks the right model for each message on your behalf. Some of its options (like the smart router) add an extra cost on top of the model itself.',
    'memory.auto': 'This memory is automatic and built from your conversations; creating it doesn\'t cost anything from your wallet — only using it in a new conversation is billed like any other message.',
    'profile.autonomy': 'This level sets how much assistants and scheduled tasks are allowed to do without your approval.',
  },
  hintOpen: 'Help',
  hintButtonLabel: '?',
}

export const guideStrings = dict(FA, EN)
