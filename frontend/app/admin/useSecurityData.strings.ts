import { dict } from '@/lib/adminI18n'

/* Error fallbacks for the two independent feeds this hook drives. See
   SecuritySection.strings.ts for the screen's own dictionary -- kept
   separate because this file is a hook, not a component. */

const FA = {
  statsError: 'خطا در دریافت آمار امنیتی',
  logsError: 'خطا در دریافت لاگ عملیات ادمین',
}

const EN: typeof FA = {
  statsError: 'Error loading security stats',
  logsError: 'Error loading the admin audit log',
}

export const useSecurityDataStrings = dict(FA, EN)
