/* ═══════════════════════════════════════════════════════════════════════════
   Shared constants for the profile page (autonomy levels, timezones).
   Split out of page.tsx to keep every file under the project's 500-line cap.
   ═══════════════════════════════════════════════════════════════════════════ */

export const AUTONOMY_LEVELS = [
  {
    value: 'low',
    label_fa: 'پایین — تأیید قبل از هر عمل',
    label_en: 'Low — Confirm before actions',
    desc_fa: 'هوش مصنوعی قبل از انجام هر عملیاتی از شما تأیید می‌گیرد. مناسب برای کاربرانی که کنترل کامل می‌خواهند.',
    desc_en: 'AI asks for your confirmation before performing any action. Suitable for users who want full control.',
    icon: 'lock',
  },
  {
    value: 'medium',
    label_fa: 'متوسط — اجرای خودکار وظایف رایج',
    label_en: 'Medium — Auto-execute common tasks',
    desc_fa: 'وظایف رایج و امن به صورت خودکار اجرا می‌شوند. اعمال حساس همچنان نیاز به تأیید دارند.',
    desc_en: 'Common and safe tasks execute automatically. Sensitive actions still require confirmation.',
    icon: 'settings',
  },
  {
    value: 'high',
    label_fa: 'بالا — خودمختاری کامل با محدودیت‌های امنیتی',
    label_en: 'High — Full autonomy with safety limits',
    desc_fa: 'هوش مصنوعی با بیشترین آزادی عمل می‌کند. فقط اعمال غیرقابل‌برگشت نیاز به تأیید دارند.',
    desc_en: 'AI operates with maximum freedom. Only irreversible actions require confirmation.',
    icon: 'rocket',
  },
]

export const TIMEZONES = [
  { value: 'Asia/Tehran', label_fa: 'تهران (IRST)', label_en: 'Tehran (IRST)' },
  { value: 'Asia/Dubai', label_fa: 'دوبی (GST)', label_en: 'Dubai (GST)' },
  { value: 'Europe/London', label_fa: 'لندن (GMT)', label_en: 'London (GMT)' },
  { value: 'America/New_York', label_fa: 'نیویورک (EST)', label_en: 'New York (EST)' },
  { value: 'Asia/Tokyo', label_fa: 'توکیو (JST)', label_en: 'Tokyo (JST)' },
  { value: 'UTC', label_fa: 'UTC', label_en: 'UTC' },
]
