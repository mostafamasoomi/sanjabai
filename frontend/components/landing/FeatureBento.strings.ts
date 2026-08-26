import { dict } from '@/lib/i18n'

const FA = {
  eyebrow: 'امکانات',
  title: 'هر چه لازم دارید، بدون اضافه‌کاری',
  lead: 'یک فضای کاری برای همه‌ی مدل‌ها: چت، ساخت عامل، حافظه‌ی بلندمدت، خروجی پاورپوینت و Word، وظایف زمان‌بندی‌شده، مقایسه‌ی خروجی و مدیریت کلیدهای API — همه در یک جا و با یک صورتحساب.',
}

const EN: typeof FA = {
  eyebrow: 'Features',
  title: 'Everything you need, nothing extra',
  lead: 'One workspace for every model: chat, building agents, long-term memory, PowerPoint and Word output, scheduled tasks, comparing outputs, and API key management — all in one place, on one bill.',
}

export const featureBentoStrings = dict(FA, EN)
