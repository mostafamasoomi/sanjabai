import { dict } from '@/lib/adminI18n'

/* Dictionary for MonitoringCharts.tsx — hand-rolled SVG/div charts used by
 * MonitoringTab.tsx. recharts is banned in this project (AdminCharts.tsx);
 * this file only translates labels, never touches the drawing code. */

const FA = {
  empty: 'داده‌ای ثبت نشده است',
  trafficTooltip: (hour: string, total: string, errors: string) => `${hour}: ${total} درخواست، ${errors} خطا`,
  volumeTooltip: (day: string, requests: string, revenue: string) => `${day}: ${requests} درخواست، ${revenue}`,
  // The ":00" suffix on an hour label ("۱۴:۰۰" / "14:00") — kept here so the
  // .tsx file never carries a raw Persian-digit literal outside a dictionary.
  minutesZero: '۰۰',
}

const EN: typeof FA = {
  empty: 'No data recorded',
  trafficTooltip: (hour, total, errors) => `${hour}: ${total} requests, ${errors} errors`,
  volumeTooltip: (day, requests, revenue) => `${day}: ${requests} requests, ${revenue}`,
  minutesZero: '00',
}

export const monitoringChartsStrings = dict(FA, EN)
