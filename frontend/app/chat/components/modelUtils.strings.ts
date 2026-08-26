import { dict } from '@/lib/i18n'
import type { HealthStatus } from '@/types/catalog'

/* modelUtils.ts is not a component -- these are plain Records/strings
   consumed via healthLabel(lang)/formatPriceIRT(value, lang) rather than a
   `const s = xStrings(lang)` call inside a render. See lib/i18n.ts for why
   `EN: typeof FA` (and no `as const` on FA) is what makes a missing key a
   build error. */

const FA = {
  health: {
    healthy: 'سالم',
    degraded: 'ناپایدار',
    down: 'در دسترس نیست',
    unknown: 'نامشخص',
  } as Record<HealthStatus, string>,
  // Price is already in tomans. The Persian unit used to read "تومان/۱M": a
  // Persian word, a slash, then a Latin M, which the RTL run reorders.
  // Spelled out in Persian it is unambiguous.
  priceUnit: 'تومان/میلیون',
}

const EN: typeof FA = {
  health: {
    healthy: 'Healthy',
    degraded: 'Degraded',
    down: 'Unavailable',
    unknown: 'Unknown',
  },
  // The English string is already fully Latin, so it has no reordering
  // problem to worry about.
  priceUnit: 'Toman/million',
}

export const modelUtilsStrings = dict(FA, EN)
