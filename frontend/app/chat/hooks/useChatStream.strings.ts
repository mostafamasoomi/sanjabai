import { dict } from '@/lib/i18n'

const FA = {
  selectModelFirst: 'لطفاً یک مدل را انتخاب کنید.',
  serverError: (status: number) => `خطای سرور: ${status}`,
  upstreamErrorFallback: 'دریافت پاسخ از سرویس با خطا مواجه شد. لطفاً دوباره تلاش کنید.',
  generationStopped: 'تولید متوقف شد.',
  connectionError: 'خطا در ارتباط',
}

const EN: typeof FA = {
  selectModelFirst: 'Please select a model.',
  serverError: (status: number) => `Server error: ${status}`,
  upstreamErrorFallback: 'Something went wrong getting a response from the service. Please try again.',
  generationStopped: 'Generation stopped.',
  connectionError: 'Connection error',
}

export const useChatStreamStrings = dict(FA, EN)
