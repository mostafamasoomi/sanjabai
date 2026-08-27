import { dict } from '@/lib/i18n'

/* Dictionary for the chart kit (LineChart / BarChart / WindowSelector).
 * Same contract as every *.strings.ts here (see lib/i18n.ts): FA is declared
 * WITHOUT `as const` — its inferred shape types EN, so a missing, extra or
 * mistyped key is a compile error; `as const` would narrow every value to a
 * literal and force EN to equal the Persian text. All numbers arrive here
 * already formatted through fmt(lang), never as raw digits. */

const FA = {
  empty: 'داده‌ای برای نمایش نیست',
  // Suffix appended to the legend label of a derived/estimated series so it
  // is never read as measured data.
  estimatedSuffix: ' (تخمینی)',
  windowGroupLabel: 'بازه زمانی نمودار',
  windowDays: (n: string) => `${n} روز`,
  windowOptionAria: (n: string) => `نمایش ${n} روز اخیر`,
}

const EN: typeof FA = {
  empty: 'No data to display',
  estimatedSuffix: ' (estimated)',
  windowGroupLabel: 'Chart time window',
  windowDays: (n) => `${n} days`,
  windowOptionAria: (n) => `Show last ${n} days`,
}

export const chartsStrings = dict(FA, EN)
