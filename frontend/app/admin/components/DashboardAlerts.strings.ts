import { dict } from '@/lib/i18n'

/* Dictionary for the dashboard's alerts card (DashboardAlerts.tsx). Same
 * contract as every *.strings.ts here (see lib/i18n.ts): FA without
 * `as const`, EN annotated with `typeof FA` so a key drift is a compile
 * error.
 *
 * Every alert line is data-derived (see deriveAlerts in DashboardAlerts.tsx)
 * — nothing here invents a number, it only phrases one that already came
 * back from GET /admin/analytics/timeseries. */

const FA = {
  title: 'هشدارها',
  empty: 'چیزی برای گزارش نیست',
  negativeMargin: (model: string, margin: string) =>
    `حاشیه ناخالص مدل «${model}» در این بازه منفی است: ${margin}`,
  lowCoverage: (percent: string) =>
    `پوشش هزینه ثبت‌شدهٔ بالادست در سی روز اخیر فقط ${percent} است`,
  errorSpike: (day: string, count: string) =>
    `افزایش غیرعادی رویدادهای خطا در محاسبهٔ هزینه — ${day}: ${count} رویداد`,
  unknownSpike: (day: string, count: string) =>
    `افزایش غیرعادی رویدادهای بدون هزینهٔ ثبت‌شده — ${day}: ${count} رویداد`,
}

const EN: typeof FA = {
  title: 'Alerts',
  empty: 'Nothing to report',
  negativeMargin: (model, margin) =>
    `Model "${model}" has a negative gross margin this window: ${margin}`,
  lowCoverage: (percent) =>
    `Only ${percent} of the last 30 days' upstream cost is recorded`,
  errorSpike: (day, count) =>
    `Unusual spike in cost-calculation error events — ${day}: ${count}`,
  unknownSpike: (day, count) =>
    `Unusual spike in unrecorded-cost events — ${day}: ${count}`,
}

export const dashboardAlertsStrings = dict(FA, EN)
