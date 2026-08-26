import { dict } from '@/lib/i18n'

const FA = {
  generating: 'در حال تولید...',
  waitingForModel: 'منتظر انتخاب مدل',
  ready: 'آماده',
  newChatShortcut: 'چت جدید',
  stopShortcut: 'توقف',
  promptCompletionTitle: (prompt: string, completion: string) => `پرامپت: ${prompt} | پاسخ: ${completion}`,
  tokenUnit: 'توکن',
  tomanUnit: 'تومان',
  lowBalance: 'موجودی کم',
  lowBalanceTitle: 'موجودی کم — شارژ کنید',
  promptLibrary: 'پرامپت‌ها',
  promptLibraryTitle: 'کتابخانه پرامپت',
  characters: (n: string) => `${n} کاراکتر`,
}

const EN: typeof FA = {
  generating: 'Generating...',
  waitingForModel: 'Waiting for a model',
  ready: 'Ready',
  newChatShortcut: 'New chat',
  stopShortcut: 'Stop',
  promptCompletionTitle: (prompt, completion) => `Prompt: ${prompt} | Completion: ${completion}`,
  tokenUnit: 'tokens',
  tomanUnit: 'Toman',
  lowBalance: 'Low balance',
  lowBalanceTitle: 'Low balance — top up',
  promptLibrary: 'Prompts',
  promptLibraryTitle: 'Prompt library',
  characters: (n) => `${n} characters`,
}

export const chatComposerFooterStrings = dict(FA, EN)
