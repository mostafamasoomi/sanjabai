import { dict } from '@/lib/i18n'

const FA = {
  title: 'تنظیمات هوش مصنوعی',
  defaultModel: 'مدل پیش‌فرض',
  selectModel: '— انتخاب مدل —',
  modelsLoadError: 'خطا در بارگذاری فهرست مدل‌ها.',
  retry: 'تلاش مجدد',
  defaultModelHint: 'مدل پیش‌فرض برای چت‌های جدید',
  personality: 'شخصیت / دستورالعمل هوش مصنوعی',
  personalityPlaceholder: 'مثال: تو یک دستیار فنی هستی. پاسخ‌ها را مختصر و فنی بده...',
  personalityHint: 'این دستورالعمل به عنوان سیستم پرامپت در هر چت جدید ارسال می‌شود',
  pinnedContext: 'یادداشت دائمی (قابل استفاده در همه چت‌ها)',
  uploadMd: 'آپلود فایل md',
  pinnedContextPlaceholder: 'یادداشتی که می‌خواهی هوش مصنوعی همیشه بداند — مثلاً پروژه‌هایت، اصطلاحات تیمت، یا محتوای یک فایل md. برخلاف حافظه‌های خودکار، این متن کامل در هر چت جدید تزریق می‌شود.',
  pinnedContextHint: (chars: string) => `این یادداشت (تا ۶۰۰۰ کاراکتر ابتدایی آن) در تمام چت‌ها و مستقل از دستیار انتخابی تزریق می‌شود. ${chars} / ۲۰٬۰۰۰ کاراکتر`,
}

const EN: typeof FA = {
  title: 'AI Preferences',
  defaultModel: 'Default Model',
  selectModel: '— Select model —',
  modelsLoadError: 'Failed to load the model list.',
  retry: 'Retry',
  defaultModelHint: 'Default model for new chats',
  personality: 'AI Personality / Instructions',
  personalityPlaceholder: 'Example: You are a technical assistant. Keep responses concise and technical...',
  personalityHint: 'This instruction is sent as a system prompt in every new chat',
  pinnedContext: 'Pinned context (used in every chat)',
  uploadMd: 'Upload .md file',
  pinnedContextPlaceholder: "Anything you want the AI to always know — your projects, team jargon, or the contents of an .md file. Unlike auto-extracted memories, this whole note is injected into every new chat.",
  pinnedContextHint: (chars) => `This note (up to its first 6000 characters) is injected into every chat regardless of the selected assistant. ${chars}/20,000 characters`,
}

export const aiPreferencesSectionStrings = dict(FA, EN)
