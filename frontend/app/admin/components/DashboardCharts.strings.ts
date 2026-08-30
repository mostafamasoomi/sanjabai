import { dict } from '@/lib/i18n'

/* Dictionary for the dashboard's two sparkline cards (DashboardCharts.tsx).
 * Same contract as every *.strings.ts (see lib/i18n.ts): FA without
 * `as const`, EN annotated with `typeof FA` so a key drift is a compile
 * error. The «۳۰» in the titles is fixed copy, not a formatted value — the
 * dashboard's window is pinned to 30 days; the full analytics page owns the
 * selectable window.
 *
 * No `loadError` here: DashboardCharts is presentational now (data fetched
 * once by DashboardSection.tsx and passed down) — the load-failure copy
 * lives in DashboardSection.strings.ts's `seriesLoadError`. */

const FA = {
  consumptionTitle: 'روند مصرف — ۳۰ روز اخیر',
  consumptionLegend: 'مصرف روزانه',
  consumptionAria: 'نمودار کوچک مصرف روزانه در سی روز اخیر',
  newUsersTitle: 'ثبت‌نام‌های جدید — ۳۰ روز اخیر',
  newUsersLegend: 'ثبت‌نام روزانه',
  newUsersAria: 'نمودار کوچک ثبت‌نام‌های روزانه در سی روز اخیر',
  openAnalytics: 'تحلیل کامل',
}

const EN: typeof FA = {
  consumptionTitle: 'Consumption trend — last 30 days',
  consumptionLegend: 'Daily consumption',
  consumptionAria: 'Sparkline of daily consumption over the last 30 days',
  newUsersTitle: 'New signups — last 30 days',
  newUsersLegend: 'Daily signups',
  newUsersAria: 'Sparkline of daily signups over the last 30 days',
  openAnalytics: 'Full analytics',
}

export const dashboardChartsStrings = dict(FA, EN)
