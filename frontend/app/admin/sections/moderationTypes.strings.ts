import { dict } from '@/lib/adminI18n'

/* Dictionary backing moderationTypes.ts's label helpers (severityLabel,
 * decisionLabel, actionLabel). moderationTypes.ts is not a component and
 * cannot call useLang(), so its label maps live here instead — the only
 * place in this feature's non-component code Persian is allowed. */

const FA = {
  severity: { low: 'پایین', medium: 'متوسط', high: 'بالا', critical: 'بحرانی' } as Record<string, string>,
  decision: { allow: 'مجاز', flag: 'پرچم‌گذاری', block: 'مسدود' } as Record<string, string>,
  action: { warn: 'هشدار', restrict: 'محدودسازی', suspend: 'تعلیق' } as Record<string, string>,
}

const EN: typeof FA = {
  severity: { low: 'Low', medium: 'Medium', high: 'High', critical: 'Critical' },
  decision: { allow: 'Allowed', flag: 'Flagged', block: 'Blocked' },
  action: { warn: 'Warn', restrict: 'Restrict', suspend: 'Suspend' },
}

export const moderationTypesStrings = dict(FA, EN)
