import { dict } from '@/lib/i18n'

/* Sibling to StatusSections.tsx. See lib/i18n.ts for why `EN: typeof FA`
   (and the absence of `as const` on FA) is what makes a missing key a
   build error. */

const FA = {
  incidentStarted: (t: string) => `شروع: ${t}`,
  servicesTitle: 'وضعیت سرویس‌ها',
  monitoringUnavailable: 'پایش بیرونی در دسترس نیست',
  staleNotice: 'داده‌ها ممکن است به‌روز نباشند',
  supportTitle: 'پشتیبانی',
  supportDesc: 'در صورت مشاهده‌ی اختلال یا سوال، از راه‌های زیر با ما در تماس باشید.',
  justNow: 'همین الان',
  minutesAgo: (n: string) => `${n} دقیقه پیش`,
  hoursAgo: (n: string) => `${n} ساعت پیش`,
  daysAgo: (n: string) => `${n} روز پیش`,
  // Non-Latin percent sign; no bidi isolation needed in an RTL run.
  percentSign: '٪',
}

const EN: typeof FA = {
  incidentStarted: (t) => `Started: ${t}`,
  servicesTitle: 'Service status',
  monitoringUnavailable: 'External monitoring unavailable',
  staleNotice: 'Data may be out of date',
  supportTitle: 'Support',
  supportDesc: 'If you notice an outage or have a question, reach us through the channels below.',
  justNow: 'just now',
  minutesAgo: (n) => `${n} min ago`,
  hoursAgo: (n) => `${n}h ago`,
  daysAgo: (n) => `${n}d ago`,
  percentSign: '%',
}

export const statusSectionsStrings = dict(FA, EN)
