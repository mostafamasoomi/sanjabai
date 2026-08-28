/* ═══════════════════════════════════════════════════════════════════════════
   Shared constants for the profile page (autonomy levels, timezones).
   Split out of page.tsx to keep every file under the project's 500-line cap.
   ═══════════════════════════════════════════════════════════════════════════ */

/* User shape as returned by /api/auth/profile and /api/auth/me. Mirrors the
   (unexported) `User` type in lib/auth.tsx -- duplicated rather than
   imported since that file doesn't export it and isn't in this packet's
   scope. Profile components should type their `user` prop with this
   instead of `any`. */
export type ProfileUser = {
  id: number
  email: string
  is_admin?: boolean
  created_at?: string
  referral_code?: string
  display_name?: string
  avatar_url?: string
  bio?: string
  preferences?: Record<string, any>
  timezone?: string
  language?: string
}

/* What each level actually does, as of 2026-08-28.
 *
 * Until phase 8 this setting was stored, validated, echoed back to this page,
 * and read by nothing -- so its three descriptions described a product that
 * did not exist ("only irreversible actions require confirmation" asked about
 * nothing, because nothing ever asked). services/chat_tools.py's
 * announced_tools() gives it a real consumer, and this copy now says what that
 * consumer does and no more.
 *
 * Two invariants hold at EVERY level and are deliberately repeated in the
 * copy, because a user choosing "high" is entitled to know what it does not
 * hand over: a task the model creates is always inactive until the user
 * activates it, and an assistant it creates is always private. */
export const AUTONOMY_LEVELS = [
  {
    value: 'low',
    label_fa: 'پایین — فقط پیشنهاد، بدون ساخت',
    label_en: 'Low — suggests only, never creates',
    desc_fa: 'ابزارهای ساخت اصلاً به مدل معرفی نمی‌شوند؛ مدل فقط می‌تواند مدل‌های در دسترس را فهرست کند و به شما بگوید خودتان کجا بروید. هیچ چیزی ساخته نمی‌شود.',
    desc_en: 'The creating tools are not even offered to the model. It can list the available models and tell you where to go build something yourself. Nothing is created.',
    icon: 'lock',
  },
  {
    value: 'medium',
    label_fa: 'متوسط — پیش‌نویس می‌کند، شما تأیید می‌کنید',
    label_en: 'Medium — drafts it, you confirm',
    desc_fa: 'مدل می‌تواند وظیفه یا دستیار پیشنهاد بدهد، ولی به‌جای ساختن، یک کارت تأیید در گفتگو نشان می‌دهد. تا وقتی روی آن کلیک نکنید هیچ چیزی ساخته نمی‌شود. پیش‌فرض.',
    desc_en: 'The model can propose a task or an assistant, but instead of creating it you get a confirmation card in the conversation. Nothing exists until you click it. The default.',
    icon: 'settings',
  },
  {
    value: 'high',
    label_fa: 'بالا — بدون پرسیدن می‌سازد',
    label_en: 'High — creates without asking',
    desc_fa: 'وظیفه و دستیار بدون تأیید شما ساخته می‌شوند. دو چیز در این سطح هم عوض نمی‌شود: وظیفهٔ ساخته‌شده غیرفعال است تا خودتان فعالش کنید، و دستیار ساخته‌شده خصوصی است.',
    desc_en: 'Tasks and assistants are created without asking you. Two things do not change even here: a created task stays inactive until you activate it, and a created assistant stays private.',
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
