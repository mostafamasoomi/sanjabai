import { dict } from '@/lib/i18n'

const FA = {
  heading: 'مهارت‌های فعال',
  activeBadge: (active: string, max: string) => `${active} از ${max} مهارت فعال`,
  // Split around the bold span rather than one string with embedded HTML —
  // this file has no JSX, only .tsx components may render markup.
  noticeBefore: 'هر مهارتی که فعال کنید، به‌طور خودکار به ',
  noticeStrong: 'تمام پیام‌های',
  noticeAfter:
    ' شما اضافه می‌شود — نه فقط وقتی از آن استفاده می‌کنید. این یعنی همان توکن‌های اضافه در هر پیام مصرف و از کیف پول شما کسر می‌شود. مهارتی که استفاده نمی‌کنید را غیرفعال نگه دارید.',
  toggleFailedEnable: 'فعال‌سازی مهارت ناموفق بود',
  toggleFailedDisable: 'غیرفعال‌سازی مهارت ناموفق بود',
  toggleSuccessEnable: 'مهارت فعال شد',
  toggleSuccessDisable: 'مهارت غیرفعال شد',
  serverError: 'خطا در ارتباط با سرور',
  loadErrorText: 'خطا در دریافت مهارت‌های فعال.',
  retry: 'تلاش دوباره',
  emptyText: 'هنوز هیچ مهارتی ندارید تا فعال کنید.',
  createFromTop: 'ایجاد مهارت جدید از بالای صفحه',
  enableAction: 'فعال کردن',
  disableAction: 'غیرفعال کردن',
  capHint: (max: string) => `برای فعال کردن این مهارت، ابتدا یکی از ${max} مهارت فعال را غیرفعال کنید`,
}

const EN: typeof FA = {
  heading: 'Active skills',
  activeBadge: (active, max) => `${active} of ${max} active`,
  noticeBefore: 'Any skill you enable is automatically added to ',
  noticeStrong: 'every message',
  noticeAfter:
    " you send — not just when you use it. That means the extra tokens are consumed and deducted from your wallet on every single turn. Keep skills you don't use disabled.",
  toggleFailedEnable: 'Failed to enable skill',
  toggleFailedDisable: 'Failed to disable skill',
  toggleSuccessEnable: 'Skill enabled',
  toggleSuccessDisable: 'Skill disabled',
  serverError: 'Server connection error',
  loadErrorText: 'Failed to load active skills.',
  retry: 'Retry',
  emptyText: "You don't have any skills to activate yet.",
  createFromTop: 'Create a new skill from the top of the page',
  enableAction: 'Enable',
  disableAction: 'Disable',
  capHint: (max) => `To enable this skill, first disable one of your ${max} active skills`,
}

export const skillActivationPanelStrings = dict(FA, EN)
