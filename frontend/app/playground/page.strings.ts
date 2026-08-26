import { dict } from '@/lib/i18n'

const FA = {
  subtitle: 'یک درخواست واقعی به /v1/chat/completions بفرستید و پاسخ خام API را ببینید',
  model: 'مدل',
  systemPromptPlaceholder: 'system prompt (اختیاری)',
  promptPlaceholder: 'prompt خود را بنویسید...',
  sending: 'در حال ارسال...',
  send: 'ارسال درخواست',
  noModelsTitle: 'مدلی در دسترس نیست',
  noModelsDesc: 'فهرست مدل‌ها خالی است.',
  response: 'پاسخ',
  request: 'درخواست (curl)',
  copy: 'کپی',
  copied: 'کد کپی شد',
  receiving: 'در حال دریافت پاسخ...',
  placeholder: 'پاسخ مدل در اینجا نمایش داده می‌شود',
  rawJson: 'پاسخ خام JSON',
  tokensInput: 'توکن ورودی',
  tokensOutput: 'توکن خروجی',
  tokensTotal: 'مجموع',
  serverError: (status: string) => `خطای سرور: ${status}`,
  connectionError: 'خطا در ارتباط',
}

const EN: typeof FA = {
  subtitle: 'Send a real request to /v1/chat/completions and inspect the raw API response',
  model: 'Model',
  systemPromptPlaceholder: 'System prompt (optional)',
  promptPlaceholder: 'Write your prompt...',
  sending: 'Sending...',
  send: 'Send request',
  noModelsTitle: 'No models available',
  noModelsDesc: 'The model list is empty.',
  response: 'Response',
  request: 'Request (curl)',
  copy: 'Copy',
  copied: 'Code copied',
  receiving: 'Receiving response...',
  placeholder: 'The model’s response will appear here',
  rawJson: 'Raw JSON response',
  tokensInput: 'Input tokens',
  tokensOutput: 'Output tokens',
  tokensTotal: 'Total',
  serverError: (status) => `Server error: ${status}`,
  connectionError: 'Connection error',
}

export const playgroundPageStrings = dict(FA, EN)
