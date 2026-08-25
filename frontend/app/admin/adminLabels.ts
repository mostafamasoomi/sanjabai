/* Bilingual label dictionary for the admin panel shell.
 *
 * The rest of the panel's 30+ section files are Persian-only by design --
 * out of scope here. This file only covers what AdminPanel.tsx itself owns:
 * the sidebar nav labels, the models/pricing sub-tab labels, and the small
 * amount of chrome text (login screen, sidebar caption, toasts) that lives
 * directly in AdminPanel.tsx.
 *
 * Shape: every bilingual entry keeps its existing `label` field as the
 * Persian string (unchanged, so files outside this task's scope that already
 * read `.label` -- e.g. ModelsModule.tsx reading `MODELS_TABS[i].label` --
 * keep compiling and rendering exactly as before) and adds a sibling
 * `labelEn` field. `t()` picks whichever the active language calls for and
 * falls back to Persian for an unknown or absent language, matching
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
