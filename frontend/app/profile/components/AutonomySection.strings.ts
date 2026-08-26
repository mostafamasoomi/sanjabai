import { dict } from '@/lib/i18n'

const FA = {
  title: 'سطح خودمختاری',
  intro: 'سطح آزادی عمل هوش مصنوعی را تنظیم کنید. این تنظیم مشخص می‌کند هوش مصنوعی چقدر بدون تأیید شما عمل کند.',
}

const EN: typeof FA = {
  title: 'Autonomy Level',
  intro: 'Set how much freedom the AI has to act on your behalf. This controls when the AI asks for confirmation.',
}

export const autonomySectionStrings = dict(FA, EN)
