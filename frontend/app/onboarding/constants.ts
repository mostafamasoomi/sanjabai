import { type Goal } from './types'

export const GOALS: Goal[] = [
  {
    id: 'coding',
    label: 'کدنویسی',
    icon: 'code',
    hint: 'تولید، دیباگ و بازنویسی کد',
    keywords: ['code', 'coding', 'developer', 'programming'],
    fallbackModel: 'Claude Sonnet 4',
    fallbackProvider: 'Anthropic',
  },
  {
    id: 'writing',
    label: 'نوشتن',
    icon: 'chat',
    hint: 'محتوا، متن و ایدهپردازی',
    keywords: ['writing', 'creative', 'content', 'copy'],
    fallbackModel: 'GPT-4o',
    fallbackProvider: 'OpenAI',
  },
  {
    id: 'translation',
    label: 'ترجمه',
    icon: 'search',
    hint: 'ترجمه روان چندزبانه',
    keywords: ['translation', 'translate', 'multilingual', 'language'],
    fallbackModel: 'Gemini 1.5 Pro',
    fallbackProvider: 'Google',
  },
  {
    id: 'analysis',
    label: 'تحلیل',
    icon: 'dashboard',
    hint: 'داده، منطق و استنتاج',
    keywords: ['analysis', 'reasoning', 'data', 'research'],
    fallbackModel: 'OpenAI o1',
    fallbackProvider: 'OpenAI',
  },
  {
    id: 'general',
    label: 'چت عمومی',
    icon: 'models',
    hint: 'گفتگوی آزاد و پرسوجو',
    keywords: ['chat', 'general', 'conversation', 'assistant'],
    fallbackModel: 'GPT-4o mini',
    fallbackProvider: 'OpenAI',
  },
]

export const STEP_LABELS = ['خوشآمد', 'هدف شما', 'انتخاب مدل', 'مدل پیشنهادی', 'نکات سریع']

export const FAVORITES_KEY = 'sanjabai_favorite_models'
