import { dict } from '@/lib/i18n'

const FA = {
  pillText: 'دسترسی مستقیم به ۲۳ مدل پیشرفته',
  titleHighlight: '۲۳ مدل هوش مصنوعی،',
  lead: 'با DeepSeek، Mistral، Gemini، Llama و ۱۹ مدل دیگر در یک فضای کاری فارسی کار کنید. مدل ایده‌آل را بیابید و همه را با یک API به محصول خودتان وصل کنید — با پرداخت به تومان و بدون نیاز به فیلترشکن.',
  ctaPrimary: 'شروع رایگان',
  ctaSecondary: 'مشاهده‌ی مدل‌ها',
  previewTabsAria: 'انتخاب مدل',
  youLabel: 'شما',
  unknownAvatar: '؟',
  modelLabel: 'مدل:',
  costNote: 'هزینه‌ی تخمینی هر پیام، پیش از ارسال نمایش داده می‌شود',
}

const EN: typeof FA = {
  pillText: 'Direct access to 23 advanced models',
  titleHighlight: '23 AI models,',
  lead: 'Work with DeepSeek, Mistral, Gemini, Llama, and 19 more models in one Persian-first workspace. Find the ideal model for the job and connect them all to your product with one API — pay in Toman, no VPN needed.',
  ctaPrimary: 'Start for free',
  ctaSecondary: 'View models',
  previewTabsAria: 'Select a model',
  youLabel: 'You',
  unknownAvatar: '?',
  modelLabel: 'Model:',
  costNote: 'Estimated cost per message is shown before you send',
}

export const heroStrings = dict(FA, EN)
