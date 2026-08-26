import { dict } from '@/lib/i18n'

/* Dictionary for ModerationSection.tsx — the moderation review queue and its
 * per-user risk modal. See moderationTypes.ts for the severity/decision/
 * action label helpers, which are language-parameterized separately because
 * that file cannot call `useLang()`. */

const FA = {
  title: 'پالایش محتوا',
  subtitle: 'صف بازبینی جستجوهای ممنوعه، قوانین تشخیص و اقدام روی کاربر',
  eventsLoadError: 'خطا در دریافت صف بازبینی',
  riskLoadError: 'خطا در دریافت وضعیت ریسک کاربر',
  actionError: 'خطا در ثبت اقدام',

  tabQueue: 'صف بازبینی',
  tabRules: 'قوانین',

  severityLabel: 'شدت',
  decisionLabel: 'تصمیم',
  searchLabel: 'جستجو',
  searchPlaceholder: 'ایمیل کاربر یا متن قطعه...',
  allOption: 'همه',

  colUser: 'کاربر',
  colCategory: 'دسته‌بندی',
  colSeverity: 'شدت',
  colDecision: 'تصمیم',
  colSnippet: 'قطعه متن',
  colTime: 'زمان',
  noEvents: 'رویدادی با این فیلترها یافت نشد',

  pageInfo: (page: string, pageCount: string, total: string) => `صفحه ${page} از ${pageCount} — ${total} رویداد`,
  prevPage: 'قبلی',
  nextPage: 'بعدی',

  riskModalTitle: (email: string) => `وضعیت ریسک — ${email}`,
  userFallback: (uid: string) => `کاربر #${uid}`,
  riskScore: 'امتیاز ریسک',
  eventCount: 'تعداد رویداد',
  recentEvents: 'رویدادهای اخیر',
  noRecentEvents: 'رویدادی ثبت نشده',
  userAction: 'اقدام روی کاربر',
  reasonLabel: (action: string) => `دلیل ${action} (الزامی)`,
  reasonPlaceholder: 'دلیل این اقدام را بنویسید...',
  submitAction: 'ثبت اقدام',
  cancel: 'انصراف',
  actionRecorded: (action: string) => `${action} ثبت شد`,
}

const EN: typeof FA = {
  title: 'Content moderation',
  subtitle: 'Review queue for prohibited searches, detection rules and user actions',
  eventsLoadError: 'Failed to fetch the review queue',
  riskLoadError: "Failed to fetch the user's risk status",
  actionError: 'Failed to record the action',

  tabQueue: 'Review queue',
  tabRules: 'Rules',

  severityLabel: 'Severity',
  decisionLabel: 'Decision',
  searchLabel: 'Search',
  searchPlaceholder: 'User email or snippet text...',
  allOption: 'All',

  colUser: 'User',
  colCategory: 'Category',
  colSeverity: 'Severity',
  colDecision: 'Decision',
  colSnippet: 'Snippet',
  colTime: 'Time',
  noEvents: 'No events match these filters',

  pageInfo: (page, pageCount, total) => `Page ${page} of ${pageCount} — ${total} events`,
  prevPage: 'Previous',
  nextPage: 'Next',

  riskModalTitle: (email) => `Risk status — ${email}`,
  userFallback: (uid) => `User #${uid}`,
  riskScore: 'Risk score',
  eventCount: 'Event count',
  recentEvents: 'Recent events',
  noRecentEvents: 'No events recorded',
  userAction: 'Action on user',
  reasonLabel: (action) => `Reason for ${action} (required)`,
  reasonPlaceholder: 'Write the reason for this action...',
  submitAction: 'Submit action',
  cancel: 'Cancel',
  actionRecorded: (action) => `${action} recorded`,
}

export const moderationSectionStrings = dict(FA, EN)
