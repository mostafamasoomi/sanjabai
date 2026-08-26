import { dict } from '@/lib/i18n'

/* Sibling to page.tsx. See lib/i18n.ts for why `EN: typeof FA` (and the
   absence of `as const` on FA) is what makes a missing key a build error.

   `tier` is a local English mirror of getModelTier's Persian labels — a
   page-local heuristic derived from the model id substring, not backend
   data, so it is translated here rather than left as a "backend-sourced"
   field. */

const FA = {
  eyebrow: 'تعرفه مدل‌ها',
  heroTitle: 'قیمت‌گذاری شفاف، پرداخت به ازای مصرف',
  heroSubtitle:
    'هر مدل هوش مصنوعی قیمت مشخصی دارد. فقط به اندازه مصرف واقعی خود پرداخت کنید. قیمت‌ها به تومان به ازای هر ۱ میلیون توکن هستند.',
  loadErrorToast: 'خطا در دریافت اطلاعات مدل‌ها',
  balanceLabel: 'موجودی کیف پول:',
  topUp: 'شارژ کیف پول',
  colModel: 'مدل',
  colInput: 'ورودی/میلیون',
  colOutput: 'خروجی/میلیون',
  colTier: 'سطح',
  noModelsFound: 'مدلی یافت نشد',
  unitNoteTitle: 'واحد قیمت',
  unitNotePrefix: 'قیمت‌ها به',
  unitNoteToman: 'تومان',
  unitNoteMiddle: 'به ازای هر',
  unitNoteTokens: '۱ میلیون توکن',
  unitNoteSuffix: 'هستند.',
  messageEstimate: (min: string, max: string) => `یک پیام معمولی حدود ${min}-${max} توکن مصرف می‌کند.`,
  topUpNoteTitle: 'شارژ کیف پول',
  topUpNoteBody: 'کیف پول خود را شارژ کنید و به ازای مصرف واقعی هر پیام، هزینه از موجودی کسر می‌شود. بدون اشتراک ماهانه!',
  smartNoteTitle: 'مدل هوشمند',
  smartNoteBody: 'با حالت «Smart»، سیستم بهترین مدل را بر اساس پیام شما انتخاب می‌کند تا بهترین کیفیت و هزینه را داشته باشید.',
  ctaTitle: 'آماده شروع هستید؟',
  ctaSubtitle: 'کیف پول خود را شارژ کنید و همین الان با هوش مصنوعی چت کنید.',
  ctaLoginAndStart: 'ورود و شروع',
  ctaTopUp: 'شارژ کیف پول',
  ctaStartChat: 'شروع چت',
  tier: {
    economy: 'اقتصادی',
    fast: 'سریع',
    advanced: 'پیشرفته',
    pro: 'حرفه‌ای',
  },
}

const EN: typeof FA = {
  eyebrow: 'Model pricing',
  heroTitle: 'Transparent pricing, pay for what you use',
  heroSubtitle:
    'Every AI model has a set price. Pay only for what you actually use. Prices are in Toman per 1 million tokens.',
  loadErrorToast: 'Failed to load model pricing',
  balanceLabel: 'Wallet balance:',
  topUp: 'Top up wallet',
  colModel: 'Model',
  colInput: 'Input / million',
  colOutput: 'Output / million',
  colTier: 'Tier',
  noModelsFound: 'No models found',
  unitNoteTitle: 'Price unit',
  unitNotePrefix: 'Prices are in',
  unitNoteToman: 'Toman',
  unitNoteMiddle: 'per',
  unitNoteTokens: '1 million tokens',
  unitNoteSuffix: '.',
  messageEstimate: (min, max) => `A typical message uses about ${min}-${max} tokens.`,
  topUpNoteTitle: 'Top up wallet',
  topUpNoteBody: 'Top up your wallet and pay from your balance for each message’s actual usage. No monthly subscription.',
  smartNoteTitle: 'Smart model',
  smartNoteBody: 'With "Smart" mode, the system picks the best model for your message for the best quality and cost.',
  ctaTitle: 'Ready to get started?',
  ctaSubtitle: 'Top up your wallet and start chatting with AI right now.',
  ctaLoginAndStart: 'Sign in and start',
  ctaTopUp: 'Top up wallet',
  // Updated to drop the "free" claim — no model on this platform is free,
  // including free-upstream supply, per product rule (see CLAUDE.md). Was
  // previously a faithful translation of FA's "شروع چت رایگان"; both sides
  // changed together to stay consistent.
  ctaStartChat: 'Start chat',
  tier: {
    economy: 'Economy',
    fast: 'Fast',
    advanced: 'Advanced',
    pro: 'Pro',
  },
}

export const pricingPageStrings = dict(FA, EN)
