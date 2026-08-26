import { type Goal } from './types'

export const GOALS: Goal[] = [
  {
    id: 'coding',
    label_fa: 'کدنویسی',
    label_en: 'Coding',
    icon: 'code',
    hint_fa: 'تولید، دیباگ و بازنویسی کد',
    hint_en: 'Generating, debugging and rewriting code',
    keywords: ['code', 'coding', 'developer', 'programming'],
    fallbackModel: 'Claude Sonnet 4',
    fallbackProvider: 'Anthropic',
  },
  {
    id: 'writing',
    label_fa: 'نوشتن',
    label_en: 'Writing',
    icon: 'chat',
    hint_fa: 'محتوا، متن و ایده‌پردازی',
    hint_en: 'Content, copy and brainstorming',
    keywords: ['writing', 'creative', 'content', 'copy'],
    fallbackModel: 'GPT-4o',
    fallbackProvider: 'OpenAI',
  },
  {
    id: 'translation',
    label_fa: 'ترجمه',
    label_en: 'Translation',
    icon: 'search',
    hint_fa: 'ترجمه روان چندزبانه',
    hint_en: 'Fluent multilingual translation',
    keywords: ['translation', 'translate', 'multilingual', 'language'],
    fallbackModel: 'Gemini 1.5 Pro',
    fallbackProvider: 'Google',
  },
  {
    id: 'analysis',
    label_fa: 'تحلیل',
    label_en: 'Analysis',
    icon: 'dashboard',
    hint_fa: 'داده، منطق و استنتاج',
    hint_en: 'Data, logic and reasoning',
    keywords: ['analysis', 'reasoning', 'data', 'research'],
    fallbackModel: 'OpenAI o1',
    fallbackProvider: 'OpenAI',
  },
  {
    id: 'general',
    label_fa: 'چت عمومی',
    label_en: 'General chat',
    icon: 'models',
    hint_fa: 'گفتگوی آزاد و پرسش‌وپاسخ',
    hint_en: 'Free-form conversation and Q&A',
    keywords: ['chat', 'general', 'conversation', 'assistant'],
    fallbackModel: 'GPT-4o mini',
    fallbackProvider: 'OpenAI',
  },
]

export const STEP_LABELS_FA = ['خوش‌آمد', 'هدف شما', 'انتخاب مدل', 'مدل پیشنهادی', 'نکات سریع']
export const STEP_LABELS_EN = ['Welcome', 'Your goal', 'Pick models', 'Recommendation', 'Quick tips']

export const FAVORITES_KEY = 'sanjabai_favorite_models'
