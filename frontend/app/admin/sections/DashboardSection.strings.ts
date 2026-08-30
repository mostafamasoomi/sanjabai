import { dict } from '@/lib/i18n'

const FA = {
  title: 'داشبورد',
  subtitle: 'نمای کلی کاربران، درآمد و مصرف',
  loadError: 'خطا در دریافت آمار داشبورد',
  // GET /admin/analytics/timeseries — the second resource this page fetches,
  // feeding the sparkline charts, the promoted margin/coverage/بازگشتی cards
  // and the alerts + per-model table below. A separate error message from
  // `loadError` above because the two are independent fetches with
  // independent failure/retry (see useAdminResource's "three distinguishable
  // states" contract in ../useAdminResource.ts).
  seriesLoadError: 'خطا در دریافت روند و آمار تفصیلی داشبورد',
  totalUsers: 'کل کاربران',
  activeUsers: 'کاربران فعال',
  totalRevenue: 'درآمد کل',
  tokensUsed: 'توکن مصرفی',
  conversations: 'گفتگوها',
  zeroPrice: '۰ تومان',
  zeroCount: '۰',
  // Promoted from the analytics deep-dive (AnalyticsCharts.tsx) — same
  // fields (`totals.usage_margin` / `totals.cost_coverage`), same
  // null-honesty rule: a not-fully-cost-measured window renders
  // «اندازه‌گیری‌نشده», never «۰ تومان» / «۰٪».
  usageMargin: 'حاشیه ناخالص مصرف (۳۰ روز)',
  costCoverage: 'پوشش هزینهٔ بالادست (۳۰ روز)',
  // Churn-proxy for a wallet/pay-as-you-go product — there is no
  // subscription to churn, so this replaces that concept. Null when the
  // window had zero purchasers (nothing to take a rate OF); rendered with
  // the same honesty word, never «۰٪».
  returningPurchaserRate: 'نرخ خریداران بازگشتی (۳۰ روز)',
  unmeasured: 'اندازه‌گیری‌نشده',
  // Distinct from `unmeasured`: this is "the series hasn't loaded yet", not
  // "the backend measured this bucket as null". Conflating the two would
  // hide a real, load-bearing loading state behind a data-honesty word.
  pending: '—',
  recentTransactions: 'تراکنش‌های اخیر',
  transactionCount: (n: string) => `(${n} مورد)`,
  colUserId: 'شناسه کاربر',
  colAmount: 'مبلغ',
  colDescription: 'شرح',
  colDate: 'تاریخ',
  noTransactions: 'تراکنشی ثبت نشده',
}

const EN: typeof FA = {
  title: 'Dashboard',
  subtitle: 'Overview of users, revenue and usage',
  loadError: 'Failed to load dashboard stats',
  seriesLoadError: 'Failed to load dashboard trend data',
  totalUsers: 'Total users',
  activeUsers: 'Active users',
  totalRevenue: 'Total revenue',
  tokensUsed: 'Tokens used',
  conversations: 'Conversations',
  zeroPrice: '0 Toman',
  zeroCount: '0',
  usageMargin: 'Gross usage margin (30d)',
  costCoverage: 'Upstream cost coverage (30d)',
  returningPurchaserRate: 'Returning purchaser rate (30d)',
  unmeasured: 'Unmeasured',
  pending: '—',
  recentTransactions: 'Recent transactions',
  transactionCount: (n) => `(${n})`,
  colUserId: 'User ID',
  colAmount: 'Amount',
  colDescription: 'Description',
  colDate: 'Date',
  noTransactions: 'No transactions recorded',
}

export const dashboardStrings = dict(FA, EN)
