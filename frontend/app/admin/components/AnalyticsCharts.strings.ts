import { dict } from '@/lib/i18n'

/* Dictionary for the full analytics surface (AnalyticsCharts.tsx). Same
 * contract as every *.strings.ts here (see lib/i18n.ts): FA is declared
 * WITHOUT `as const` so its inferred shape types EN, and a key drift is a
 * compile error.
 *
 * Two wording rules in this file are load-bearing, not stylistic:
 *
 *   1. `unmeasured` is what a NULL margin renders as. The backend returns
 *      `usage_margin: null` for any bucket that is not fully cost-measured
 *      (backend/admin_analytics_timeseries.py::margin_or_none), and the UI
 *      must say so — never «۰ تومان», which would draw a fake-profitable
 *      past out of unmeasured history.
 *
 *   2. Nothing here may call the margin «سود خالص». revenue − upstream cost
 *      is GROSS margin on token cost; it excludes the fixed infrastructure
 *      cost, and the backend enforces the same rule on its field names. */

const FA = {
  kpiConsumption: 'مصرف کاربران (بازه انتخابی)',
  kpiGateway: 'درآمد درگاه (بازه انتخابی)',
  kpiKnownCost: 'هزینه ثبت‌شده بالادست',
  kpiMargin: 'حاشیه ناخالص مصرف',
  unmeasured: 'اندازه‌گیری‌نشده',
  marginDisclaimer:
    'حاشیه ناخالص یعنی مصرف منهای هزینه ثبت‌شده توکن بالادست. هزینه ثابت زیرساخت را در بر نمی‌گیرد و سود خالص نیست.',
  coverageTitle: 'پوشش هزینه این بازه ناقص است',
  coverageBody: (percent: string) =>
    `فقط ${percent} از مصرف این بازه هزینه بالادستِ ثبت‌شده دارد؛ به همین دلیل حاشیه ناخالص «اندازه‌گیری‌نشده» نمایش داده می‌شود، نه صفر.`,
  cutoverNote: (date: string) =>
    `اندازه‌گیری هزینه بالادست از ${date} آغاز شده و رویدادهای پیش از آن هزینه ثبت‌شده ندارند.`,
  eventCounts: (unknown: string, error: string) =>
    `رویدادهای بدون هزینه در این بازه: ${unknown} نامشخص، ${error} خطا`,
  moneyTitle: 'پول در مقیاس مشترک',
  moneyAria: 'نمودار خطی مصرف، درآمد درگاه، هزینه بالادست و حاشیه ناخالص روزانه',
  legendConsumption: 'مصرف کاربران',
  legendGateway: 'درآمد درگاه',
  legendKnownCost: 'هزینه ثبت‌شده بالادست',
  legendMargin: 'حاشیه ناخالص',
  growthTitle: 'رشد کاربران',
  growthAria: 'نمودار ستونی ثبت‌نام‌های جدید و خریداران روزانه',
  legendNewUsers: 'ثبت‌نام جدید',
  legendPurchasers: 'خریدار',
  convTitle: 'رشد گفتگوها',
  convAria: 'نمودار خطی تعداد گفتگوهای ساخته‌شده در هر روز',
  legendConversations: 'گفتگوهای جدید',
  tokensTitle: 'حجم توکن',
  tokensAria: 'نمودار ستونی انباشته توکن ورودی و خروجی روزانه',
  legendInputTokens: 'توکن ورودی',
  legendOutputTokens: 'توکن خروجی',
  modelTableTitle: 'مصرف به تفکیک مدل (بازه انتخابی)',
  userTableTitle: 'کاربران پرمصرف (بازه انتخابی)',
  colModel: 'مدل',
  colUser: 'کاربر',
  colConsumption: 'مصرف',
  colKnownCost: 'هزینه ثبت‌شده',
  colCoverage: 'پوشش هزینه',
  colMargin: 'حاشیه ناخالص',
  colUsers: 'کاربران',
  colCalls: 'فراخوانی',
  colTokens: 'توکن',
  noRows: 'موردی در این بازه ثبت نشده',
}

const EN: typeof FA = {
  kpiConsumption: 'User consumption (selected window)',
  kpiGateway: 'Gateway revenue (selected window)',
  kpiKnownCost: 'Known upstream cost',
  kpiMargin: 'Gross usage margin',
  unmeasured: 'Unmeasured',
  marginDisclaimer:
    'Gross margin is consumption minus the recorded upstream token cost. It excludes fixed infrastructure cost and is not net profit.',
  coverageTitle: 'Cost coverage for this window is incomplete',
  coverageBody: (percent) =>
    `Only ${percent} of this window's consumption has a recorded upstream cost; that is why the gross margin shows as “Unmeasured”, not zero.`,
  cutoverNote: (date) =>
    `Upstream cost measurement began on ${date}; events before that carry no recorded cost.`,
  eventCounts: (unknown, error) =>
    `Events without a cost in this window: ${unknown} unknown, ${error} errored`,
  moneyTitle: 'Money on a shared scale',
  moneyAria: 'Line chart of daily consumption, gateway revenue, upstream cost and gross margin',
  legendConsumption: 'User consumption',
  legendGateway: 'Gateway revenue',
  legendKnownCost: 'Known upstream cost',
  legendMargin: 'Gross margin',
  growthTitle: 'User growth',
  growthAria: 'Bar chart of daily new signups and buyers',
  legendNewUsers: 'New signups',
  legendPurchasers: 'Buyers',
  convTitle: 'Conversation growth',
  convAria: 'Line chart of conversations created per day',
  legendConversations: 'New conversations',
  tokensTitle: 'Token volume',
  tokensAria: 'Stacked bar chart of daily input and output tokens',
  legendInputTokens: 'Input tokens',
  legendOutputTokens: 'Output tokens',
  modelTableTitle: 'Consumption by model (selected window)',
  userTableTitle: 'Top users (selected window)',
  colModel: 'Model',
  colUser: 'User',
  colConsumption: 'Consumption',
  colKnownCost: 'Known cost',
  colCoverage: 'Cost coverage',
  colMargin: 'Gross margin',
  colUsers: 'Users',
  colCalls: 'Calls',
  colTokens: 'Tokens',
  noRows: 'Nothing recorded in this window',
}

export const analyticsChartsStrings = dict(FA, EN)
