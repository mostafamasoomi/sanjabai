import { dict } from '@/lib/i18n'

/* Titles/descriptions describe each template so a user can browse and search
   the library — that is UI copy, translated normally. The `prompt` field
   itself (in page.tsx's PROMPTS array) is the text sent to the model when
   the card is clicked; per the i18n spec that is CONTENT the user picked
   because it is Persian, not chrome, so it is left Persian-only in both
   languages here. See the report for the full reasoning. */

const FA = {
  headerTitle: 'کتابخانه پرامپت',
  headerSubtitle: 'پرامپت‌های آماده فارسی برای شروع سریع گفتگو',
  searchPlaceholder: 'جستجوی پرامپت...',
  clearSearchAria: 'پاک کردن',
  allCategories: 'همه',
  categories: {
    coding: 'کدنویسی',
    translation: 'ترجمه',
    analysis: 'تحلیل',
    creativity: 'خلاقیت',
    general: 'عمومی',
  },
  countBase: (n: string) => `${n} پرامپت`,
  countInCategory: (cat: string) => ` در دسته «${cat}»`,
  countForSearch: (q: string) => ` برای «${q}»`,
  emptyText: 'پرامپتی با این مشخصات یافت نشد',
  clearFilters: 'پاک کردن فیلترها',
  useAction: 'استفاده از پرامپت',
  prompts: {
    p1: { title: 'نوشتن کد پایتون', description: 'یک تابع یا اسکریپت پایتون با توضیحات کامل و بهینه' },
    p2: { title: 'ترجمه فارسی به انگلیسی', description: 'ترجمه روان و دقیق متن فارسی به انگلیسی' },
    p3: { title: 'تحلیل داده‌های متنی', description: 'تحلیل و استخراج الگوها و اطلاعات کلیدی از متن' },
    p4: { title: 'ایده‌پردازی خلاقانه', description: 'تولید ایده‌های خلاقانه برای پروژه‌ها و کسب‌وکارها' },
    p5: { title: 'خلاصه‌سازی متن', description: 'خلاصه‌سازی هوشمند متن‌های طولانی به نکات اصلی' },
    p6: { title: 'بررسی باگ و رفع اشکال', description: 'تحلیل کد و پیدا کردن باگ‌ها با پیشنهاد راه‌حل' },
    p7: { title: 'بازنویسی محتوا', description: 'بازنویسی و بهبود متن با حفظ معنی اصلی' },
    p8: { title: 'ترجمه انگلیسی به فارسی', description: 'ترجمه تخصصی و روان انگلیسی به فارسی' },
    p9: { title: 'تحلیل SWOT', description: 'تحلیل نقاط قوت، ضعف، فرصت‌ها و تهدیدها' },
    p10: { title: 'توضیح مفاهیم پیچیده', description: 'توضیح ساده و قابل فهم مفاهیم علمی و تخصصی' },
  },
}

const EN: typeof FA = {
  headerTitle: 'Prompt library',
  headerSubtitle: 'Ready-made prompts to start a conversation quickly',
  searchPlaceholder: 'Search prompts...',
  clearSearchAria: 'Clear',
  allCategories: 'All',
  categories: {
    coding: 'Coding',
    translation: 'Translation',
    analysis: 'Analysis',
    creativity: 'Creativity',
    general: 'General',
  },
  countBase: (n) => `${n} prompts`,
  countInCategory: (cat) => ` in “${cat}”`,
  countForSearch: (q) => ` for “${q}”`,
  emptyText: 'No prompts match these filters',
  clearFilters: 'Clear filters',
  useAction: 'Use prompt',
  prompts: {
    p1: { title: 'Write Python code', description: 'A Python function or script with clear, optimized documentation' },
    p2: { title: 'Persian to English translation', description: 'Fluent, accurate translation of Persian text into English' },
    p3: { title: 'Text data analysis', description: 'Analyze text and extract key patterns and information' },
    p4: { title: 'Creative brainstorming', description: 'Generate creative ideas for projects and businesses' },
    p5: { title: 'Text summarization', description: 'Smart summarization of long text into key points' },
    p6: { title: 'Bug review and fixing', description: 'Analyze code, find bugs, and suggest fixes' },
    p7: { title: 'Content rewriting', description: 'Rewrite and improve text while keeping the original meaning' },
    p8: { title: 'English to Persian translation', description: 'Expert, fluent translation of English into Persian' },
    p9: { title: 'SWOT analysis', description: 'A full SWOT analysis: strengths, weaknesses, opportunities, threats' },
    p10: { title: 'Explain complex concepts', description: 'Simple, clear explanations of scientific and technical concepts, with examples' },
  },
}

export const promptsPageStrings = dict(FA, EN)
