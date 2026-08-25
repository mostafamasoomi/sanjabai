import { dict } from '@/lib/adminI18n'

const FA = {
  title: 'سربار پروایدرهای بالادست',
  subtitle:
    'مقدار توکنی که هر مسیر بالادست (بدون درخواست کاربر) به هر پیام اضافه می‌کند — کاربر امروز بابت همهٔ این توکن‌ها هزینه می‌دهد',

  liveMeasurementTitle: 'اندازه‌گیری زنده',
  measuring: (elapsed: string) => `در حال اندازه‌گیری… (${elapsed})`,
  measureButton: 'اندازه‌گیری زنده',
  measureHint:
    'این اندازه‌گیری درخواست واقعی به مسیرهای بالادست می‌زند و ممکن است بیش از یک دقیقه طول بکشد — تا پایان صبر کنید، قطع نشده.',
  lastSaved: (date: string, time: string) => `آخرین ذخیره‌سازی: ${date} — ${time}`,

  // formatElapsedSeconds — the seconds/minutes counter on the measure button.
  elapsedSeconds: (n: string) => `${n} ثانیه`,
  elapsedMinutes: (n: string) => `${n} دقیقه`,
  elapsedMinutesSeconds: (m: string, s: string) => `${m} دقیقه و ${s} ثانیه`,

  contractMismatchTitle: 'پاسخ سرور با قرارداد مورد انتظار مطابقت ندارد',
  contractMismatchHint:
    'این با «هنوز چیزی اندازه‌گیری نشده» فرق دارد — یعنی ساختار پاسخ backend عوض شده و این صفحه نمی‌تواند آن را بخواند. قبل از اعتماد به هر عددی در جدول زیر، این را برطرف کنید.',
  retry: 'تلاش دوباره',

  statMeasuredRoutes: 'مسیرهای دارای اندازه‌گیری اختصاصی',
  statRequests7d: 'درخواست ۷ روز اخیر (مجموع پروایدرها)',
  statTokensDiscounted7d: 'توکن کسرشده ۷ روز اخیر (مجموع)',

  measuredEntriesTitle: 'مسیرهای اندازه‌گیری‌شده — overhead اختصاصی',
  measuredEntriesSubtitle: 'هر ردیف مستقیماً اندازه‌گیری شده — عدد سربار آن از پیش‌فرض هیچ پروایدری ارث نمی‌برد.',

  loading: 'در حال بارگذاری…',
  noData: 'اطلاعاتی در دسترس نیست',

  inertTitle: 'نقشهٔ سربار هنوز خالی است — این حالت پیش‌فرض همان چیزی است که با آن منتشر شده‌ایم.',
  inertBody:
    'یعنی کسر سربار هنوز غیرفعال است و فعلاً هیچ کاربری بابت سربار مسیر بالادست هزینهٔ اضافه نمی‌دهد. برای پر شدن این جدول و فعال شدن کسر واقعی، روی «اندازه‌گیری زنده» بزنید.',

  noRouteRecorded: (dateTime: string) => `آخرین اندازه‌گیری (${dateTime}) هیچ مسیری را با موفقیت ثبت نکرد.`,

  colRoute: 'مسیر',
  colProvider: 'پروایدر',
  colOverheadTokens: 'سربار (توکن)',
  colSampleModel: 'مدل نمونه',
  colMeasuredAt: 'زمان اندازه‌گیری',
  colDetails: 'جزئیات',

  close: 'بستن',
  howComputed: 'نحوهٔ محاسبه',
  noDetails: 'بدون جزئیات',
  rawNumbersHint:
    'اعداد خامی که سربار از روی آن‌ها محاسبه شده — یک عدد بدون این‌ها، یعنی معلوم نیست چرا مبلغ هر کاربر تغییر کرده.',
  labelP1: 'p۱',
  labelP2: 'p۲',
  labelC1: 'c۱',
  labelC2: 'c۲',
  labelSlope: 'شیب (slope)',

  providerDefaultsTitle: 'پیش‌فرض هر پروایدر — fallback برای مسیرهای اندازه‌گیری‌نشده',
  providerDefaultsSubtitle:
    'این عدد فقط برای پیشوندی از این پروایدر که در جدول بالا اندازه‌گیری اختصاصی ندارد اعمال می‌شود — با overhead اختصاصی هر مسیر یکی نیست.',
  colDefaultOverheadTokens: 'سربار پیش‌فرض (توکن)',

  statsTitle: 'آمار ۷ روز اخیر به تفکیک پروایدر',
  statsSubtitle: 'این آمار به ازای پروایدر است، نه هر مسیر — چند مسیر می‌توانند یک ردیف آماری مشترک داشته باشند.',
  colRequests7d: 'درخواست ۷ روز',
  colTokensDiscounted7d: 'توکن کسرشده ۷ روز',

  loadErrorToast: 'خطا در دریافت اطلاعات سربار پروایدرها',
  measureFailedToast: 'اندازه‌گیری سربار ناموفق بود',
  measureDoneWithCounts: (measured: string, skipped: string | null) =>
    `اندازه‌گیری زنده تمام شد — ${measured} مسیر اندازه‌گیری شد${skipped ? `، ${skipped} مسیر رد شد` : ''}`,
  measureDoneGeneric: 'اندازه‌گیری زنده سربار به‌روزرسانی شد',
}

const EN: typeof FA = {
  title: 'Upstream provider overhead',
  subtitle:
    'The number of tokens each upstream route adds to every message on top of what the user actually wrote — the user is currently charged for all of it',

  liveMeasurementTitle: 'Live measurement',
  measuring: (elapsed) => `Measuring… (${elapsed})`,
  measureButton: 'Measure live',
  measureHint:
    'This sends real requests to the upstream routes and can take over a minute — wait for it to finish, it has not stalled.',
  lastSaved: (date, time) => `Last saved: ${date} — ${time}`,

  elapsedSeconds: (n) => `${n} seconds`,
  elapsedMinutes: (n) => `${n} minutes`,
  elapsedMinutesSeconds: (m, s) => `${m} minutes ${s} seconds`,

  contractMismatchTitle: 'The server response does not match the expected contract',
  contractMismatchHint:
    'This is different from "nothing has been measured yet" — the backend response shape has changed and this page cannot read it. Fix this before trusting any number in the table below.',
  retry: 'Retry',

  statMeasuredRoutes: 'Routes with a dedicated measurement',
  statRequests7d: 'Requests, last 7 days (all providers)',
  statTokensDiscounted7d: 'Tokens discounted, last 7 days (total)',

  measuredEntriesTitle: 'Measured routes — dedicated overhead',
  measuredEntriesSubtitle:
    'Each row was measured directly — its overhead value does not inherit from any provider default.',

  loading: 'Loading…',
  noData: 'No data available',

  inertTitle: 'The overhead map is still empty — this is the default state we shipped with.',
  inertBody:
    'That means overhead deduction is still disabled and no user is currently paying extra for upstream route overhead. To fill this table and turn on the real deduction, click "Measure live".',

  noRouteRecorded: (dateTime) => `The last measurement (${dateTime}) did not record any route successfully.`,

  colRoute: 'Route',
  colProvider: 'Provider',
  colOverheadTokens: 'Overhead (tokens)',
  colSampleModel: 'Sample model',
  colMeasuredAt: 'Measured at',
  colDetails: 'Details',

  close: 'Close',
  howComputed: 'How it was computed',
  noDetails: 'No details',
  rawNumbersHint:
    "The raw numbers the overhead was computed from — a bare number without these leaves no way to tell why a user's charge changed.",
  labelP1: 'p1',
  labelP2: 'p2',
  labelC1: 'c1',
  labelC2: 'c2',
  labelSlope: 'Slope',

  providerDefaultsTitle: 'Per-provider default — fallback for unmeasured routes',
  providerDefaultsSubtitle:
    "This value only applies to a prefix under this provider that has no dedicated measurement in the table above — it is not the same as any route's own overhead.",
  colDefaultOverheadTokens: 'Default overhead (tokens)',

  statsTitle: 'Last 7 days, by provider',
  statsSubtitle: 'This is per provider, not per route — several routes can share one stats row.',
  colRequests7d: 'Requests, 7d',
  colTokensDiscounted7d: 'Tokens discounted, 7d',

  loadErrorToast: 'Failed to load upstream overhead data',
  measureFailedToast: 'Live measurement failed',
  measureDoneWithCounts: (measured, skipped) =>
    `Live measurement finished — ${measured} route${measured === '1' ? '' : 's'} measured${skipped ? `, ${skipped} skipped` : ''}`,
  measureDoneGeneric: 'Live overhead measurement updated',
}

export const upstreamOverheadStrings = dict(FA, EN)
