import { dict } from '@/lib/i18n'

/* The reference dictionary — every other *.strings.ts in this directory
   follows this shape. See lib/i18n.ts for why `EN: typeof FA` (and the
   absence of `as const` on FA) is what makes a missing key a build error. */

const FA = {
  searchPlaceholder: 'جستجو در نام، شناسه، تأمین‌کننده…',
  allAvailability: 'همهٔ وضعیت‌ها',
  allModels: 'همهٔ مدل‌ها',
  probeConfirmed: 'پروب تأییدشده',
  probeUnconfirmed: 'بدون پروب موفق',
  probeReady: 'آمادهٔ ارائه (پروب + قیمت + شناسهٔ عمومی)',
  reload: 'بازخوانی',
  // Interpolated rather than concatenated at the call site: word order
  // between the two numbers is not the same in both languages.
  matched: (shown: string, total: string) => `${shown} از ${total} مدل مطابق فیلتر`,
  available: 'در دسترس',
  degraded: 'کاهش‌یافته',
  maintenance: 'در تعمیر',
  disabled: 'غیرفعال',
  confirmed: 'پروب تأییدشده',
  healthyUnserved: 'سالم ولی ارائه‌نشده',
  ready: 'آمادهٔ ارائه',
}

const EN: typeof FA = {
  searchPlaceholder: 'Search name, id, provider…',
  allAvailability: 'All statuses',
  allModels: 'All models',
  probeConfirmed: 'Probe confirmed',
  probeUnconfirmed: 'No successful probe',
  probeReady: 'Ready to serve (probe + price + public id)',
  reload: 'Reload',
  matched: (shown, total) => `${shown} of ${total} models match the filter`,
  available: 'Available',
  degraded: 'Degraded',
  maintenance: 'Maintenance',
  disabled: 'Disabled',
  confirmed: 'Probe confirmed',
  healthyUnserved: 'Healthy but unserved',
  ready: 'Ready to serve',
}

export const catalogFilterStrings = dict(FA, EN)
