import { dict } from '@/lib/i18n'

/* Persian/English pair for BulkTestSummary.tsx — see BulkLiveTest.strings.ts
 * for the pattern this follows. `groupLabel`/`groupHint` are keyed by the
 * ErrorClass union in BulkTestSummary.tsx, not spelled out per-key, so a new
 * class added there is a compile error here until both objects grow it. */
const FA = {
  title: 'خلاصهٔ نتایج تست دسته‌ای',
  summary: (tested: string, ok: string, failed: string) =>
    `${tested} مدل آزموده شد — ${ok} سالم، ${failed} ناموفق`,
  groupLabel: {
    gone: 'مدل دیگر وجود ندارد (۴۰۴)',
    rateLimited: 'محدودیت نرخ (۴۲۹)',
    accessLost: 'دسترسی از دست رفته (۴۰۱/۴۰۳)',
    noCredit: 'اعتبار حساب تمام شده (۴۰۲)',
    upstreamBroken: 'خرابی upstream (۵xx)',
    timeout: 'کندتر از بودجهٔ پروب',
    other: 'سایر خطاها',
  },
  groupHint: {
    gone: 'مدل دیگر در upstream وجود ندارد — کاتالوگ ما نسبت به آن قدیمی شده. غیرفعال‌سازی امن است.',
    rateLimited: 'حساب تأمین‌کننده موقتاً به محدودیت نرخ خورده — گذرا است، دوباره امتحان کنید.',
    accessLost: 'حساب تأمین‌کننده دسترسی خود را از دست داده — مشکل حساب است، نه مدل.',
    noCredit: 'حساب تأمین‌کننده اعتبار کافی ندارد — مشکل حساب است، نه مدل.',
    upstreamBroken: 'upstream در لحظهٔ تست خراب بوده — می‌تواند گذرا باشد.',
    timeout: 'مدل پاسخ می‌دهد ولی کندتر از بودجهٔ پروب بوده — گذرا است.',
    other: 'علتی که در دسته‌های بالا جا نمی‌شود؛ بررسی دستی لازم است.',
  },
  disableGoneAction: (count: string) => `غیرفعال کردن ${count} مدل حذف‌شده`,
  confirmDisableGone: (count: string) =>
    `${count} مدلی که دیگر در upstream وجود ندارند (۴۰۴) به «غیرفعال» تغییر می‌کنند. `
    + 'این عملیات از همین صفحه قابل بازگشت نیست. ادامه می‌دهید؟',
  disabling: 'در حال غیرفعال‌سازی…',
  disabledSuccess: (count: string) => `${count} مدل غیرفعال شد`,
  disableFailed: 'غیرفعال کردن مدل‌ها ناموفق بود',
}

const EN: typeof FA = {
  title: 'Bulk test failure summary',
  summary: (tested, ok, failed) => `${tested} models tested — ${ok} healthy, ${failed} failed`,
  groupLabel: {
    gone: 'Model gone (404)',
    rateLimited: 'Rate limited (429)',
    accessLost: 'Access lost (401/403)',
    noCredit: 'Out of credit (402)',
    upstreamBroken: 'Upstream broken (5xx)',
    timeout: 'Slower than probe budget',
    other: 'Other errors',
  },
  groupHint: {
    gone: 'The model no longer exists upstream — our catalog is stale for it. Safe to disable.',
    rateLimited: "The supplying account hit a rate limit — transient, retry later.",
    accessLost: "The supplying account lost access — an account problem, not the model's.",
    noCredit: "The supplying account is out of credit — an account problem, not the model's.",
    upstreamBroken: 'Upstream was broken at test time — may be transient.',
    timeout: 'The model answers, just slower than the probe budget — transient.',
    other: "Doesn't fit the classes above; needs manual review.",
  },
  disableGoneAction: (count) => `Disable ${count} gone models`,
  confirmDisableGone: (count) =>
    `${count} models that no longer exist upstream (404) will be set to "disabled". `
    + 'This cannot be undone from this screen. Continue?',
  disabling: 'Disabling…',
  disabledSuccess: (count) => `${count} models disabled`,
  disableFailed: 'Failed to disable models',
}

export const bulkTestSummaryStrings = dict(FA, EN)
