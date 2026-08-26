import { dict } from '@/lib/i18n'
import type { HealthSummary } from '@/types/catalog'

/* Sibling to page.tsx. See lib/i18n.ts for why `EN: typeof FA` (and the
   absence of `as const` on FA) is what makes a missing key a build error.
   Model health labels come from `healthLabel(lang)` in
   app/chat/components/modelUtils.ts (that file's own bilingual reader,
   added after this page was translated) rather than being duplicated here. */

const FA = {
  title: 'وضعیت مدل‌ها',
  subtitle:
    'سلامت هر مدل به‌صورت زنده اندازه‌گیری می‌شود — از درخواست‌های واقعی کاربران و بررسی‌های دوره‌ای.',
  subtitleWindow: (n: string) => ` بازه‌ی محاسبه: ${n} دقیقه‌ی گذشته.`,
  refresh: 'به‌روزرسانی',
  unavailableTitle: 'وضعیت در دسترس نیست',
  unavailableDesc: 'گزارش سلامت خوانده نشد. این یعنی خود سرویس وضعیت مشکل دارد، نه لزوماً مدل‌ها.',
  overall: {
    operational: 'همه‌ی سرویس‌ها فعال هستند',
    degraded: 'بخشی از مدل‌ها ناپایدار هستند',
    down: 'اختلال گسترده',
  } as Record<HealthSummary['overall'], string>,
  gateway: {
    operational: { label: 'برقرار', hint: 'همهٔ مسیرهای تأمین پاسخ می‌دهند' },
    degraded: { label: 'ناپایدار', hint: 'بخشی از مدل‌ها ممکن است پاسخ ندهند' },
    down: { label: 'قطع', hint: 'تأمین مدل در دسترس نیست' },
    unknown: { label: 'نامشخص', hint: 'وضعیت تأمین قابل تشخیص نیست' },
  } as Record<NonNullable<HealthSummary['gateways']>['status'], { label: string; hint: string }>,
  supplySection: 'تأمین مدل‌ها',
  modelsSection: 'مدل‌ها',
  colModel: 'مدل',
  colStatus: 'وضعیت',
  colSuccessRate: 'نرخ موفقیت',
  colLatency: 'تأخیر میانه',
  colSamples: 'نمونه',
  colLastEvent: 'آخرین رویداد',
  noSamples: 'هنوز نمونه‌ای ثبت نشده است. اولین بررسی دوره‌ای پس از راه‌اندازی سرویس انجام می‌شود.',
  footnote: (updated: string, seconds: string) =>
    `آخرین به‌روزرسانی: ${updated} · این صفحه هر ${seconds} ثانیه تازه می‌شود.`,
  justNow: 'همین الان',
  minutesAgo: (n: string) => `${n} دقیقه پیش`,
  hoursAgo: (n: string) => `${n} ساعت پیش`,
  daysAgo: (n: string) => `${n} روز پیش`,
}

const EN: typeof FA = {
  title: 'Model status',
  subtitle:
    'Each model’s health is measured live, from real user requests and periodic checks.',
  subtitleWindow: (n) => ` Measurement window: the last ${n} minutes.`,
  refresh: 'Refresh',
  unavailableTitle: 'Status unavailable',
  unavailableDesc:
    'The health report could not be read. This means the status service itself has a problem, not necessarily the models.',
  overall: {
    operational: 'All services are operational',
    degraded: 'Some models are unstable',
    down: 'Widespread outage',
  },
  gateway: {
    operational: { label: 'Operational', hint: 'All supply routes are responding' },
    degraded: { label: 'Degraded', hint: 'Some models may not respond' },
    down: { label: 'Down', hint: 'Model supply is unavailable' },
    unknown: { label: 'Unknown', hint: 'Supply status cannot be determined' },
  },
  supplySection: 'Model supply',
  modelsSection: 'Models',
  colModel: 'Model',
  colStatus: 'Status',
  colSuccessRate: 'Success rate',
  colLatency: 'Median latency',
  colSamples: 'Samples',
  colLastEvent: 'Last event',
  noSamples: 'No samples recorded yet. The first periodic check runs shortly after the service starts.',
  footnote: (updated, seconds) => `Last updated: ${updated} · This page refreshes every ${seconds} seconds.`,
  justNow: 'just now',
  minutesAgo: (n) => `${n} min ago`,
  hoursAgo: (n) => `${n}h ago`,
  daysAgo: (n) => `${n}d ago`,
}

export const statusPageStrings = dict(FA, EN)
