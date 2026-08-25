import { dict } from '@/lib/adminI18n'

/* Dictionary for WatchdogSection.tsx — the Telegram alert credential shared
 * by the account-lockout, financial-watchdog and content-moderation alert
 * paths (backend/security.py, watchdog.py, services/moderation_store.py). */

const FA = {
  title: 'هشدارهای تلگرام',
  subtitle: 'اعتبارنامهٔ رباتی که هشدارهای قفل‌شدن حساب، ناهنجاری مالی و پالایش محتوا با آن ارسال می‌شود — بدون نیاز به ری‌استارت',
  errorSubtitle: 'اعتبارنامهٔ رباتی که هشدارهای امنیتی، مالی و پالایش محتوا با آن ارسال می‌شود',

  loading: 'در حال بارگذاری…',
  noData: 'اطلاعاتی یافت نشد',

  loadFailedTitle: 'دریافت تنظیمات ناموفق بود',
  loadFailedGeneric: 'خطا در دریافت تنظیمات هشدار',
  loadFailedNote: 'وضعیت واقعی هشدارها نامشخص است — تا رفع خطا فرم نمایش داده نمی‌شود، چون نمایش «تنظیم نشده» وقتی حقیقت معلوم نیست می‌تواند باعث تصمیم اشتباه شود.',
  retry: 'تلاش دوباره',

  sourceDb: 'از پنل (پایگاه داده)',
  sourceEnv: 'از متغیر محیطی سرور',
  sourceNone: 'تنظیم نشده',

  statusActiveTitle: 'هشدارها فعال است',
  statusInactiveTitle: 'هشدارها ارسال نمی‌شود',
  statusActiveBody: (tokenSource: string, chatSource: string) =>
    `توکن ربات ${tokenSource} و شناسهٔ گفتگو ${chatSource} خوانده می‌شود. هر سه مسیر هشدار (قفل حساب، دیده‌بان مالی، پالایش محتوا) از همین جفت استفاده می‌کنند.`,
  statusInactiveNone: 'هیچ‌کدام از دو مقدار تنظیم نشده است — هر سه مسیر هشدار بی‌صدا رد می‌شوند.',
  statusInactiveNoToken: 'توکن ربات تنظیم نشده است — تا وقتی هر دو مقدار پر نشوند هیچ هشداری ارسال نمی‌شود.',
  statusInactiveNoChat: 'شناسهٔ گفتگو تنظیم نشده است — تا وقتی هر دو مقدار پر نشوند هیچ هشداری ارسال نمی‌شود.',

  tokenFieldLabel: 'توکن ربات تلگرام',
  tokenSet: 'تنظیم شده',
  tokenNotSet: 'تنظیم نشده',
  tokenPlaceholderReplace: 'برای جایگزینی، توکن جدید را وارد کنید',
  tokenPlaceholderNew: '123456789:AA...',
  tokenHelp: 'مقدار فعلی هرگز از سرور برگردانده نمی‌شود؛ این فیلد فقط برای نوشتن است. ذخیره‌کردن، مقدار قبلی را جایگزین می‌کند.',
  clearTokenLabel: 'پاک‌کردن توکن ذخیره‌شده',
  clearTokenWithEnv: ' — پس از پاک‌کردن، مقدار متغیر محیطی سرور دوباره به‌کار می‌رود.',
  clearTokenNoEnv: ' — متغیر محیطی هم تنظیم نیست، پس هشدارها خاموش می‌شوند.',

  chatFieldLabel: 'شناسهٔ گفتگو (chat id)',
  chatPlaceholder: '-1001234567890',
  chatHelp: 'شناسهٔ گفتگو رمز نیست، پس کامل نمایش داده می‌شود تا بتوانید درستی‌اش را بررسی کنید. خالی گذاشتن یعنی برگشتن به متغیر محیطی سرور',
  chatHelpEnvSet: '.',
  chatHelpEnvUnset: ' (که آن هم تنظیم نیست).',

  save: 'ذخیره',
  cancel: 'انصراف',
  noChanges: 'تغییری برای ذخیره وجود ندارد',
  saveOk: 'تنظیمات هشدار ذخیره شد',
  saveFailed: 'ذخیره ناموفق بود',
  serverError: (status: string) => `خطای سرور (${status})`,

  rowsMissing: (rows: string) => `ردیف‌های ذخیره‌سازی هنوز در پایگاه داده ساخته نشده‌اند (${rows}) — مهاجرت 0044 هنوز اعمال نشده است. اولین ذخیره خودش ردیف را می‌سازد.`,
  // Separator for joining `rows_missing` before interpolation into rowsMissing().
  listSeparator: '، ',

  usedWhereTitle: 'این اعتبارنامه کجا خوانده می‌شود',
  usedWhereLockout: 'قفل‌شدن حساب پس از تلاش‌های ناموفق ورود — backend/security.py',
  usedWhereWatchdog: 'دیده‌بان مالی (۱۳ قاعدهٔ CRITICAL/HIGH) — backend/watchdog.py، کانتینر جدا',
  usedWhereModeration: 'پالایش محتوا (block/flag و خطای آشکارساز) — backend/services/moderation_store.py',
  usedWherePriority: 'مقدار پنل بر متغیر محیطی اولویت دارد؛ اگر پنل خالی باشد متغیر محیطی سرور به‌کار می‌رود. اگر پایگاه داده در دسترس نباشد، هر سه مسیر به متغیر محیطی برمی‌گردند تا خطای تنظیمات هرگز مسیر گفتگو را نشکند.',
}

const EN: typeof FA = {
  title: 'Telegram alerts',
  subtitle: 'The bot credential used to send account-lockout, financial-anomaly and content-moderation alerts — no restart needed',
  errorSubtitle: 'The bot credential used to send security, financial and content-moderation alerts',

  loading: 'Loading…',
  noData: 'No data found',

  loadFailedTitle: 'Failed to fetch settings',
  loadFailedGeneric: 'Failed to fetch alert settings',
  loadFailedNote: 'The real alert status is unknown — the form stays hidden until the error is resolved, because showing "not configured" when the truth is unknown could lead to a wrong decision.',
  retry: 'Retry',

  sourceDb: 'From panel (database)',
  sourceEnv: 'From server environment variable',
  sourceNone: 'Not configured',

  statusActiveTitle: 'Alerts are active',
  statusInactiveTitle: 'Alerts are not being sent',
  statusActiveBody: (tokenSource, chatSource) =>
    `The bot token is read ${tokenSource} and the chat id ${chatSource}. All three alert paths (account lockout, financial watchdog, content moderation) use this same pair.`,
  statusInactiveNone: 'Neither value is configured — all three alert paths are silently dropped.',
  statusInactiveNoToken: 'The bot token is not configured — no alert is sent until both values are set.',
  statusInactiveNoChat: 'The chat id is not configured — no alert is sent until both values are set.',

  tokenFieldLabel: 'Telegram bot token',
  tokenSet: 'Configured',
  tokenNotSet: 'Not configured',
  tokenPlaceholderReplace: 'Enter a new token to replace it',
  tokenPlaceholderNew: '123456789:AA...',
  tokenHelp: 'The current value is never returned from the server; this field is write-only. Saving replaces the previous value.',
  clearTokenLabel: 'Clear the stored token',
  clearTokenWithEnv: ' — after clearing, the server’s environment variable takes over again.',
  clearTokenNoEnv: ' — the environment variable is not set either, so alerts will turn off.',

  chatFieldLabel: 'Chat id',
  chatPlaceholder: '-1001234567890',
  chatHelp: 'The chat id is not a secret, so it is shown in full so you can verify it. Leaving it blank means falling back to the server’s environment variable',
  chatHelpEnvSet: '.',
  chatHelpEnvUnset: ' (which is not configured either).',

  save: 'Save',
  cancel: 'Cancel',
  noChanges: 'No changes to save',
  saveOk: 'Alert settings saved',
  saveFailed: 'Save failed',
  serverError: (status) => `Server error (${status})`,

  rowsMissing: (rows) => `Storage rows have not been created in the database yet (${rows}) — migration 0044 has not been applied yet. The first save creates the row.`,
  listSeparator: ', ',

  usedWhereTitle: 'Where this credential is read',
  usedWhereLockout: 'Account lockout after failed login attempts — backend/security.py',
  usedWhereWatchdog: 'Financial watchdog (13 CRITICAL/HIGH rules) — backend/watchdog.py, separate container',
  usedWhereModeration: 'Content moderation (block/flag and detector errors) — backend/services/moderation_store.py',
  usedWherePriority: 'The panel value takes priority over the environment variable; if the panel value is empty the server’s environment variable is used. If the database is unavailable, all three paths fall back to the environment variable so a settings error never breaks the alert path.',
}

export const watchdogSectionStrings = dict(FA, EN)
