import { dict } from '@/lib/i18n'

const FA = {
  title: 'سرور هرمس',
  subtitle: 'یک سرور آماده با ایجنت هرمس، از پیش نصب‌شده — اسکیل‌هایتان (برنامه‌نویسی، رصد اخبار، ...) را انتخاب کنید و تحویل بگیرید.',
  loadError: 'خطا در دریافت پلن‌های سرور هرمس',
  emptyTitle: 'در حال حاضر پلنی موجود نیست',
  emptyDescription: 'لطفاً بعداً دوباره سر بزنید.',
  includedCredit: (price: string) => `+ ${price} اعتبار هدیه`,
  vcpu: (n: string) => `${n} هسته پردازشی`,
  ram: (n: string) => `${n} گیگابایت رم`,
  disk: (n: string) => `${n} گیگابایت دیسک`,
  traffic: (n: string) => `${n} ترابایت ترافیک`,
  maxSkills: (n: string) => `تا ${n} اسکیل هم‌زمان`,
  setupFee: (price: string) => `راه‌اندازی: ${price}`,
  perMonth: '/ ماه',
  orderThis: 'سفارش این سرور',
  loginToOrder: 'ورود برای سفارش',
  afterPurchaseTitle: 'بعد از خرید چه اتفاقی می‌افتد؟',
  afterPurchaseBody: 'پس از پرداخت، سرور برای شما راه‌اندازی و اسکیل‌های انتخابی روی هرمس نصب می‌شود. سپس می‌توانید از صفحه‌ی مدیریت سرور، اسکیل‌های جدید اضافه یا اسکیل‌های موجود را حذف کنید و کلید API اختصاصی سرورتان را برای شارژ اعتبار مصرفی مدیریت نمایید.',
}

const EN: typeof FA = {
  title: 'Hermes Server',
  subtitle: 'A ready-made server with the Hermes agent pre-installed — pick your skills (coding, news monitoring, ...) and take delivery.',
  loadError: 'Failed to load Hermes server plans',
  emptyTitle: 'No plans available right now',
  emptyDescription: 'Please check back later.',
  includedCredit: (price) => `+ ${price} bonus credit`,
  vcpu: (n) => `${n} vCPU`,
  ram: (n) => `${n} GB RAM`,
  disk: (n) => `${n} GB disk`,
  traffic: (n) => `${n} TB traffic`,
  maxSkills: (n) => `Up to ${n} concurrent skills`,
  setupFee: (price) => `Setup: ${price}`,
  perMonth: '/ mo',
  orderThis: 'Order this server',
  loginToOrder: 'Sign in to order',
  afterPurchaseTitle: 'What happens after purchase?',
  afterPurchaseBody: 'After payment, your server is provisioned and the selected skills are installed on Hermes. From the server management page you can then add new skills or remove existing ones, and manage your server’s dedicated API key to top up usage credit.',
}

export const hermesLandingStrings = dict(FA, EN)
