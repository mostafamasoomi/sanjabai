import { dict } from '@/lib/i18n'

/* Dictionary for the dashboard's per-model mini-table
 * (DashboardModelBreakdown.tsx). Same contract as every *.strings.ts here
 * (see lib/i18n.ts): FA without `as const`, EN annotated with `typeof FA` so
 * a key drift is a compile error.
 *
 * `title` says «مصرف», not «درآمد» (consumption, not revenue) — this table
 * is `consumption_by_model`, i.e. what users were charged for calling that
 * model, which is NOT gateway revenue (see the backend's own naming rule,
 * admin_analytics_timeseries.py's module docstring, and AnalyticsCharts.tsx
 * where the equivalent full table is titled `modelTableTitle`). A model has
 * no "revenue" of its own — gateway revenue comes from payments, which are
 * not attributable to a single model. Calling this "revenue by model" would
 * repeat exactly the word-blur commit 81d8240 exists to prevent. */

const FA = {
  title: 'مصرف به‌تفکیک مدل — ۳۰ روز اخیر',
  colModel: 'مدل',
  colConsumption: 'مصرف',
  colCoverage: 'پوشش هزینه',
  colMargin: 'حاشیه ناخالص',
  unmeasured: 'اندازه‌گیری‌نشده',
  noRows: 'موردی در این بازه ثبت نشده',
  openAnalytics: 'مشاهده کامل',
  moreRows: (count: string) => `و ${count} مدل دیگر در صفحهٔ تحلیل کامل`,
}

const EN: typeof FA = {
  title: 'Consumption by model — last 30 days',
  colModel: 'Model',
  colConsumption: 'Consumption',
  colCoverage: 'Cost coverage',
  colMargin: 'Gross margin',
  unmeasured: 'Unmeasured',
  noRows: 'Nothing recorded in this window',
  openAnalytics: 'View full breakdown',
  moreRows: (count) => `and ${count} more on the full analytics page`,
}

export const dashboardModelBreakdownStrings = dict(FA, EN)
