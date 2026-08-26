import { dict } from '@/lib/i18n'

const FA = {
  welcomeBackPrefix: 'خوش آمدید، ',
  welcomeToPrefix: 'به ',
  welcomeToSuffix: ' خوش آمدید',
  intro: 'چند ثانیه وقت بدهید تا همه‌چیز را برای شما آماده کنیم. فقط چند قدم ساده تا شروع چت با بهترین مدل‌های هوش مصنوعی دنیا.',
  start: 'بیا شروع کنیم',
}

const EN: typeof FA = {
  welcomeBackPrefix: 'Welcome, ',
  welcomeToPrefix: 'Welcome to ',
  welcomeToSuffix: '',
  intro: "Give us a few seconds to get everything ready. Just a couple of quick steps until you're chatting with the world's best AI models.",
  start: "Let's get started",
}

export const stepWelcomeStrings = dict(FA, EN)
