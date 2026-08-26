import { dict } from '@/lib/i18n'
import type { IconName } from '../../ui/Icon'

/* ── Features ─────────────────────────────────────────────────────────────── */

export interface Feature {
  icon: IconName
  title: string
  desc: string
  href?: string
  linkLabel?: string
}

const FA = {
  items: [
    {
      icon: 'chat',
      title: 'چت چندمدلی، بدون قطع شدن رشته‌ی گفتگو',
      desc: 'وسط مکالمه بین مدل‌ها جابه‌جا شوید. تاریخچه دست‌نخورده می‌ماند و مدل بعدی همان زمینه را می‌بیند — پس برای هر بخش از کار می‌توانید مناسب‌ترین مدل را انتخاب کنید.',
      href: '/chat',
      linkLabel: 'باز کردن چت',
    },
    {
      icon: 'sparkles',
      title: 'عامل‌هایی که کار را تا آخر می‌برند',
      desc: 'عامل بسازید، به آن مهارت و حافظه‌ی بلندمدت بدهید و ابزارهایتان را وصل کنید. کارهای تکراری را زمان‌بندی کنید و نتیجه را در داشبورد ببینید.',
      href: '/skills',
      linkLabel: 'ساخت عامل',
    },
    {
      icon: 'compare',
      title: 'مقایسه‌ی کنار هم',
      desc: 'یک پرامپت، چند مدل. کیفیت، سرعت و هزینه را در یک نگاه بسنجید.',
      href: '/compare',
      linkLabel: 'مقایسه کنید',
    },
    {
      icon: 'file',
      title: 'هوش سند',
      desc: 'سند و تصویر را آپلود کنید و درباره‌ی محتوایشان سوال بپرسید.',
      href: '/documents',
      linkLabel: 'آپلود سند',
    },
    {
      icon: 'code',
      title: 'API سازگار با OpenAI',
      desc: 'فقط آدرس پایه را عوض کنید. SDKهای فعلی‌تان بدون تغییری کار می‌کنند.',
      href: '/developer',
      linkLabel: 'مستندات API',
    },
    {
      icon: 'cpu',
      title: 'حافظه‌ای که خودش می‌سازد',
      desc: 'ترجیحات، پروژه‌ها و مهارت‌هایی که در گفتگو می‌گویید، خودکار به‌عنوان حافظه‌ی بلندمدت ذخیره می‌شود — از دفعه‌ی بعد لازم نیست دوباره توضیح دهید.',
      href: '/memory',
      linkLabel: 'مدیریت حافظه',
    },
    {
      icon: 'palette',
      title: 'خروجی آماده: پاورپوینت، Word و اسلاید',
      desc: 'یک پرامپت بدهید، فایل PPTX، Word یا اسلاید Markdown آماده‌ی دانلود بگیرید — بدون باز کردن نرم‌افزار جدا.',
      href: '/documents',
      linkLabel: 'ساخت سند',
    },
    {
      icon: 'calendar',
      title: 'وظایف زمان‌بندی‌شده',
      desc: 'یک پرامپت را روی بازه‌ی دلخواه (روزانه، هفتگی، هر چند ساعت) زمان‌بندی کنید و نتیجه را در داشبورد، ایمیل یا تلگرام دریافت کنید.',
      href: '/tasks',
      linkLabel: 'زمان‌بندی وظیفه',
    },
    {
      icon: 'chart',
      title: 'هزینه‌ی شفاف، بدون اشتراک ماهانه',
      desc: 'کیف پولتان را شارژ می‌کنید و هزینه‌ی هر درخواست به‌ازای توکن از همان کسر می‌شود. مصرف و مانده را لحظه‌ای در داشبورد می‌بینید.',
      href: '/usage',
      linkLabel: 'داشبورد مصرف',
    },
  ] satisfies Feature[],
}

const EN: typeof FA = {
  items: [
    {
      icon: 'chat',
      title: 'Multi-model chat, one unbroken thread',
      desc: 'Switch models mid-conversation. History stays intact and the next model sees the same context — so you can pick the best model for each part of the job.',
      href: '/chat',
      linkLabel: 'Open chat',
    },
    {
      icon: 'sparkles',
      title: 'Agents that see the job through',
      desc: 'Build an agent, give it skills and long-term memory, and connect your tools. Schedule repeat work and check the results from your dashboard.',
      href: '/skills',
      linkLabel: 'Build an agent',
    },
    {
      icon: 'compare',
      title: 'Side-by-side comparison',
      desc: 'One prompt, several models. Compare quality, speed, and cost at a glance.',
      href: '/compare',
      linkLabel: 'Compare models',
    },
    {
      icon: 'file',
      title: 'Document intelligence',
      desc: 'Upload a document or image and ask questions about its content.',
      href: '/documents',
      linkLabel: 'Upload a document',
    },
    {
      icon: 'code',
      title: 'OpenAI-compatible API',
      desc: 'Just change the base URL. Your existing SDKs work without any other change.',
      href: '/developer',
      linkLabel: 'API docs',
    },
    {
      icon: 'cpu',
      title: 'Memory that builds itself',
      desc: 'Preferences, projects, and skills you mention in chat are automatically saved as long-term memory — no need to re-explain them next time.',
      href: '/memory',
      linkLabel: 'Manage memory',
    },
    {
      icon: 'palette',
      title: 'Ready-to-use output: PowerPoint, Word, slides',
      desc: 'Give a prompt, get a downloadable PPTX, Word, or Markdown slide deck — no separate software to open.',
      href: '/documents',
      linkLabel: 'Generate a document',
    },
    {
      icon: 'calendar',
      title: 'Scheduled tasks',
      desc: 'Schedule a prompt on your own interval (daily, weekly, every few hours) and get the result on your dashboard, by email, or on Telegram.',
      href: '/tasks',
      linkLabel: 'Schedule a task',
    },
    {
      icon: 'chart',
      title: 'Transparent cost, no monthly subscription',
      desc: 'Top up your wallet and each request is billed per token from that balance. See usage and balance live on your dashboard.',
      href: '/usage',
      linkLabel: 'Usage dashboard',
    },
  ],
}

export const featuresContent = dict(FA, EN)
