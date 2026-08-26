/* Bilingual labels for the admin panel SHELL -- the sidebar nav, the sub-tab
 * table, the login screen and its toasts.
 *
 * This is the older of the panel's two translation shapes and it stays for
 * what it is good at: a list of items that already existed as objects
 * (`{ key, label, icon }`) and only needed a sibling field. Section bodies
 * use the other shape, `dict(FA, EN)` from lib/i18n.ts, which is what
 * to reach for when translating free-standing strings -- it makes a missing
 * key a compile error, which a `labelEn` field cannot do.
 *
 * `t()` falls back to Persian for an unknown or absent language, matching
 * LanguageToggle's own default.
 */

import type { Lang } from '@/components/LanguageToggle'

export type { Lang }

export interface Bilingual {
  label: string
  labelEn: string
}

/** Returns the label matching `lang`. Anything other than the literal
 *  string 'en' (including undefined, null, or a typo) resolves to Persian --
 *  the same default `getLang()` uses. */
export function t(item: Bilingual, lang: Lang | string | null | undefined): string {
  return lang === 'en' ? item.labelEn : item.label
}

/* Admin chrome that lives directly in AdminPanel.tsx: the sidebar caption,
 * the login screen, and its toast strings. */
export const ADMIN_CHROME = {
  panelCaption: { label: 'پنل مدیریت', labelEn: 'Admin Panel' },
  loginSubtitle: { label: 'ورود با توکن ادمین', labelEn: 'Sign in with an admin token' },
  tokenFieldLabel: { label: 'توکن ادمین', labelEn: 'Admin token' },
  tokenPlaceholder: { label: 'توکن خود را وارد کنید...', labelEn: 'Enter your token...' },
  loginButton: { label: 'ورود', labelEn: 'Sign in' },
  loggingIn: { label: 'در حال ورود...', labelEn: 'Signing in...' },
  logout: { label: 'خروج', labelEn: 'Log out' },
  sessionExpired: { label: 'نشست شما منقضی شد؛ دوباره وارد شوید', labelEn: 'Your session has expired -- please sign in again' },
  loginSuccess: { label: 'ورود موفقیت‌آمیز بود', labelEn: 'Signed in successfully' },
  invalidToken: { label: 'توکن نامعتبر است', labelEn: 'Invalid token' },
  connectionError: { label: 'خطا در اتصال به سرور', labelEn: 'Error connecting to the server' },
} as const satisfies Record<string, Bilingual>
