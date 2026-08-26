import { dict } from '@/lib/i18n'

/* Sibling to error.tsx. See lib/i18n.ts for why `EN: typeof FA` (and the
   absence of `as const` on FA) is what makes a missing key a build error. */

const FA = {
  title: 'خطای سیستمی',
  body: 'مشکلی در بارگذاری صفحه پیش آمده است.',
  errorId: (id: string) => `Error ID: ${id}`,
  retry: 'تلاش مجدد',
  home: 'بازگشت به خانه',
}

const EN: typeof FA = {
  title: 'System error',
  body: 'Something went wrong while loading this page.',
  errorId: (id) => `Error ID: ${id}`,
  retry: 'Try again',
  home: 'Back to home',
}

export const errorPageStrings = dict(FA, EN)
