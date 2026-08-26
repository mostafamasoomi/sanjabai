import { dict } from '@/lib/i18n'

/* chatHelpers.ts is not a component -- its functions take `lang` as a plain
   parameter instead of calling useLang(). See lib/i18n.ts for why
   `EN: typeof FA` (and no `as const` on FA) is what makes a missing key a
   build error. */

const FA = {
  welcomeMessage: 'سلام! به Sanjabai خوش آمدید. چطور می‌توانم کمک کنید؟',
  presetCode: { label: 'کدنویسی', description: 'نوشتن و دیباگ کد', prompt: 'یک تابع در ' },
  presetTranslate: { label: 'ترجمه', description: 'ترجمه متن به فارسی', prompt: 'متن زیر را به فارسی روان ترجمه کن:\n\n' },
  presetSummarize: { label: 'خلاصه‌سازی', description: 'خلاصه کردن متن طولانی', prompt: 'متن زیر را خلاصه کن:\n\n' },
  presetAnalyze: { label: 'تحلیل', description: 'تحلیل داده‌ها و اطلاعات', prompt: 'داده‌های زیر را تحلیل کن:\n\n' },
  justNow: 'اکنون',
  minutesAgo: (n: number) => `${n} دقیقه پیش`,
  hoursAgo: (n: number) => `${n} ساعت پیش`,
  daysAgo: (n: number) => `${n} روز پیش`,
  groupToday: 'امروز',
  groupYesterday: 'دیروز',
  groupThisWeek: 'این هفته',
  groupOlder: 'قدیمی‌تر',
  // The literal text sent as the user's own turn when they click "ادامه بده"
  // on a length-capped reply (see useChatStream's handleContinue) -- kept in
  // sync with ChatMessageItem.strings.ts's `continue` button label by hand,
  // since one is a component string and the other an actual chat message.
  continueMessage: 'ادامه بده',
}

const EN: typeof FA = {
  welcomeMessage: 'Hi! Welcome to Sanjabai. How can I help you?',
  presetCode: { label: 'Coding', description: 'Write and debug code', prompt: 'Write a function in ' },
  presetTranslate: { label: 'Translate', description: 'Translate text to Persian', prompt: 'Translate the following text into fluent Persian:\n\n' },
  presetSummarize: { label: 'Summarize', description: 'Summarize a long text', prompt: 'Summarize the following text:\n\n' },
  presetAnalyze: { label: 'Analyze', description: 'Analyze data and information', prompt: 'Analyze the following data:\n\n' },
  justNow: 'Just now',
  minutesAgo: (n) => `${n} min ago`,
  hoursAgo: (n) => `${n}h ago`,
  daysAgo: (n) => `${n}d ago`,
  groupToday: 'Today',
  groupYesterday: 'Yesterday',
  groupThisWeek: 'This week',
  groupOlder: 'Older',
  continueMessage: 'Continue',
}

export const chatHelpersStrings = dict(FA, EN)
