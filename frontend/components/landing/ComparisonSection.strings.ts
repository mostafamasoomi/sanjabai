import { dict } from '@/lib/i18n'

const FA = {
  eyebrow: 'مقایسه',
  title: 'چرا پرداخت به‌ازای مصرف، نه اشتراک ماهانه؟',
  lead: 'تفاوت سنجوبای با سرویس‌های اشتراکی رایج، در یک نگاه.',
  // Points along the reading direction: "forward" is left in RTL, right in LTR.
  scrollHint: 'برای مقایسه‌ی کامل، جدول را به چپ بکشید ⟵',
  subscriptionColumnHeading: 'سرویس‌های اشتراکی رایج',
}

const EN: typeof FA = {
  eyebrow: 'Comparison',
  title: 'Why pay per use instead of a monthly subscription?',
  lead: 'How Sanjabai compares to common subscription services, at a glance.',
  scrollHint: 'Drag the table right to see the full comparison ⟶',
  subscriptionColumnHeading: 'Common subscription services',
}

export const comparisonSectionStrings = dict(FA, EN)
