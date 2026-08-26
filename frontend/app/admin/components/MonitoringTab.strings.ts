import { dict } from '@/lib/i18n'

/* Dictionary for MonitoringTab.tsx — the read-only operator dashboard over
 * GET /admin/monitoring. See CatalogFilterBar.strings.ts for the pattern
 * and lib/i18n.ts for why `EN: typeof FA` (no `as const` on FA) is the
 * completeness check. */

const FA = {
  headerTitle: 'پایش سامانه',
  headerSubtitle: 'وضعیت زنده درگاه‌های بالادست، مدل‌ها، ترافیک و صورتحساب',
  reload: 'بازخوانی',
  loading: 'در حال بارگذاری...',
  loadError: 'خطا در بارگذاری اطلاعات پایش',
  retry: 'تلاش مجدد',
  sectionError: 'خطا در این بخش',
  noItems: 'موردی یافت نشد',
  noData: 'داده‌ای موجود نیست',

  // Per-model / per-upstream health state, keyed by the server's raw enum.
  status: {
    healthy: 'سالم', degraded: 'کاهش‌یافته', down: 'قطع', unknown: 'نامشخص',
  } as Record<string, string>,

  // KPI row
  kpiUpstreamsAlive: 'درگاه‌های بالادست فعال',
  kpiModelsDown: 'مدل‌های قطع',
  kpiKumaLabel: 'پایش بیرونی (Kuma)',
  kpiErrorRate: 'نرخ خطا (۲۴ ساعت)',
  active: 'فعال',
  down: 'قطع',
  live: 'زنده',

  // Upstreams
  upstreamsTitle: 'درگاه‌های بالادست',
  latencyPrefix: 'تأخیر:',

  // Models table
  modelsTitle: 'مدل‌ها',
  colModel: 'مدل',
  colStatus: 'وضعیت',
  colSuccessRate: 'نرخ موفقیت',
  colP50: 'P50',
  colP95: 'P95',
  colSamples: 'نمونه‌ها',
  colLastStatus: 'آخرین وضعیت',

  // Traffic / volume
  trafficTitle: 'ترافیک (۲۴ ساعت اخیر)',
  volumeTitle: 'حجم (۷ روز اخیر)',

  // Billing — shortfall
  shortfallTitle: 'صورتحساب — کسری',
  countLabel: 'تعداد:',
  shortfallSumLabel: 'مجموع کسری:',
  colUser: 'کاربر',
  colChargedAmount: 'مبلغ دریافتی',
  colListedCost: 'هزینه فهرست‌شده',
  colShortfall: 'کسری',
  colTime: 'زمان',

  // Billing — estimated
  estimatedTitle: 'صورتحساب — تخمینی',
  last24hLabel: '۲۴ ساعت اخیر:',
  last30dLabel: '۳۰ روز اخیر:',

  // Wallet
  negBalanceTitle: 'کیف پول — موجودی منفی',
  colBalance: 'موجودی',
  ledgerMismatchTitle: 'کیف پول — ناهماهنگی دفتر کل',
  colWalletBalance: 'موجودی کیف پول',
  colLedgerBalance: 'موجودی دفتر کل',
  colDelta: 'اختلاف',

  // Kuma
  kumaTitle: 'پایش بیرونی (Kuma)',
  kumaStale: 'داده قدیمی',
  kumaSourceLabel: 'منبع:',
  kumaSourceCache: 'حافظه نهان',
  kumaSourceLastGood: 'آخرین وضعیت سالم',
  kumaFailingWarning: 'هشدار: دریافت وضعیت از Kuma با خطا مواجه است',

  // Footer — interpolated so the "updated at" clause and the caching note
  // keep their Persian word order rather than being concatenated in English.
  footer: (time: string) => `به‌روزرسانی: ${time} — این داده تا ۳۰ ثانیه در سرور کش می‌شود`,
}

const EN: typeof FA = {
  headerTitle: 'System monitoring',
  headerSubtitle: 'Live status of upstreams, models, traffic and billing',
  reload: 'Reload',
  loading: 'Loading...',
  loadError: 'Failed to load monitoring data',
  retry: 'Retry',
  sectionError: 'Error in this section',
  noItems: 'No items found',
  noData: 'No data available',

  status: {
    healthy: 'Healthy', degraded: 'Degraded', down: 'Down', unknown: 'Unknown',
  },

  kpiUpstreamsAlive: 'Upstreams alive',
  kpiModelsDown: 'Models down',
  kpiKumaLabel: 'External monitoring (Kuma)',
  kpiErrorRate: 'Error rate (24h)',
  active: 'Active',
  down: 'Down',
  live: 'Live',

  upstreamsTitle: 'Upstreams',
  latencyPrefix: 'Latency:',

  modelsTitle: 'Models',
  colModel: 'Model',
  colStatus: 'Status',
  colSuccessRate: 'Success rate',
  colP50: 'P50',
  colP95: 'P95',
  colSamples: 'Samples',
  colLastStatus: 'Last status',

  trafficTitle: 'Traffic (last 24 hours)',
  volumeTitle: 'Volume (last 7 days)',

  shortfallTitle: 'Billing — shortfall',
  countLabel: 'Count:',
  shortfallSumLabel: 'Total shortfall:',
  colUser: 'User',
  colChargedAmount: 'Charged amount',
  colListedCost: 'Listed cost',
  colShortfall: 'Shortfall',
  colTime: 'Time',

  estimatedTitle: 'Billing — estimated',
  last24hLabel: 'Last 24h:',
  last30dLabel: 'Last 30d:',

  negBalanceTitle: 'Wallet — negative balances',
  colBalance: 'Balance',
  ledgerMismatchTitle: 'Wallet — ledger mismatches',
  colWalletBalance: 'Wallet balance',
  colLedgerBalance: 'Ledger balance',
  colDelta: 'Delta',

  kumaTitle: 'External monitoring (Kuma)',
  kumaStale: 'Stale data',
  kumaSourceLabel: 'Source:',
  kumaSourceCache: 'Cache',
  kumaSourceLastGood: 'Last known good',
  kumaFailingWarning: 'Warning: fetching status from Kuma is failing',

  footer: (time) => `Updated: ${time} — this data is cached on the server for up to 30 seconds`,
}

export const monitoringTabStrings = dict(FA, EN)
