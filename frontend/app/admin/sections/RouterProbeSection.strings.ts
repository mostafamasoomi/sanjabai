import { dict } from '@/lib/i18n'

/* Bilingual strings for RouterProbeSection.tsx — same `dict(FA, EN)` shape as
 * every other admin section's `.strings.ts` (see UpstreamOverheadSection.strings.ts).
 *
 * `reasonLabel`/`stateLabel` take the raw values already classified by
 * routerProbeHelpers.ts (a `RouterProbeState`, or the raw `reason` string
 * from the stored entry) and turn them into a sentence — kept here, not in
 * the helpers file, because these are display text, not a display DECISION;
 * the decision itself (which of the three outcomes a row is) is the part
 * that has to be pure and tested. */

const FA = {
  title: 'پروب پذیرش روتر هوشمند',
  subtitle:
    'اینکه هر مدل واجد شرایط «روتر بودن» است یا نه — یک نقش جدا از فروختنی‌بودن مدل به کاربر؛ فقط ۱۲ مدل ارزان‌تر استخر روتر بررسی می‌شوند.',

  liveMeasurementTitle: 'اجرای زندهٔ پروب',
  measureButton: 'اجرای پروب زنده',
  measuring: (elapsed: string) => `در حال اجرا… (${elapsed})`,
  measureHint:
    'این عملیات تا ۴۸ درخواست واقعی به مدل‌ها می‌زند (حداکثر ۴ تماس برای هر یک از ۱۲ مدل ارزان‌تر) و هزینهٔ واقعی دارد — مبلغ دقیق به قیمت زندهٔ هر مدل بستگی دارد و از پیش قابل اعلام نیست.',
  confirmRun: 'این عملیات تا ۴۸ درخواست زنده به مدل‌ها می‌زند و هزینهٔ واقعی (نامشخص، وابسته به قیمت زندهٔ هر مدل) دارد. ادامه می‌دهید؟',
  lastSaved: (date: string, time: string) => `آخرین ذخیره‌سازی: ${date} — ${time}`,

  elapsedSeconds: (n: string) => `${n} ثانیه`,
  elapsedMinutes: (n: string) => `${n} دقیقه`,
  elapsedMinutesSeconds: (m: string, s: string) => `${m} دقیقه و ${s} ثانیه`,

  measureFailedToast: 'اجرای پروب ناموفق بود',
  measureDone: (measured: string, eligible: string) => `پروب تمام شد — از ${measured} مدل بررسی‌شده، ${eligible} مورد واجد شرایط روتر شدند`,
  loadErrorToast: 'خطا در دریافت نتیجهٔ پروب روتر',
  retry: 'تلاش دوباره',

  staleWarning: (date: string, time: string) =>
    `این نتیجه مربوط به ${date} — ${time} است، بیش از ۷ روز قدیمی. روتر هوشمند همچنان همین نتیجهٔ قدیمی را معتبر می‌شمارد — قبل از اعتماد به این جدول، پروب را دوباره اجرا کنید.`,
  measuredAt: (date: string, time: string) => `آخرین اجرای پروب: ${date} — ${time}`,

  statEligible: 'واجد شرایط روتر',
  statPermanent: 'نامناسب دائمی',
  statTransient: 'نامعلوم — خطای موقت',

  neverMeasuredTitle: 'این پروب تا کنون هرگز اجرا نشده است.',
  neverMeasuredBody:
    'یعنی هیچ مدلی هنوز برای «روتر بودن» بررسی نشده — نه اینکه همه رد شده باشند. برای پر شدن این جدول روی «اجرای پروب زنده» بزنید.',
  loading: 'در حال بارگذاری…',
  noData: 'اطلاعاتی در دسترس نیست',

  colModel: 'شناسهٔ عمومی مدل',
  colState: 'وضعیت',
  colReason: 'دلیل',
  colRetryAfter: 'تلاش دوباره در',
  colLastRecorded: 'آخرین ثبت',

  stateEligible: 'واجد شرایط',
  stateIneligiblePermanent: 'نامناسب (دائمی)',
  stateIneligibleTransient: 'نامعلوم (موقتی)',

  reasonBadShape: 'شکل پاسخ نامعتبر بود — مدل به منوی ساختگی، پاسخ قابل‌قبول نداد.',
  reasonNoDiscrimination: 'بین یک پیام سلام و یک پیام استدلالی فرق نمی‌گذارد.',
  reasonProviderNotConfigured: 'پروایدر این مدل در حال حاضر پیکربندی نشده است.',
  reasonTransientTimeout: 'بالادست به‌موقع پاسخ نداد — این یک خطای موقتی است، نه قضاوتی دربارهٔ خود مدل.',
  reasonTransientException: 'خطای ارتباطی موقت با بالادست — قضاوتی دربارهٔ خود مدل نیست.',
  reasonTransientHttp: (code: string) => `بالادست خطای HTTP ${code} برگرداند — این یک نوسان موقتی شناخته‌شده است، نه قضاوتی دربارهٔ خود مدل.`,
  reasonUnknown: (raw: string) => `دلیل ثبت‌شده: ${raw}`,
  sampleReplyLabel: 'پاسخ نمونهٔ ثبت‌شده',
  noReason: '—',
  noRetry: '—',
}

const EN: typeof FA = {
  title: 'Smart-router acceptance probe',
  subtitle:
    'Whether each model qualifies as a router — a different role from being sellable to a user; only the 12 cheapest pool members are scanned.',

  liveMeasurementTitle: 'Live probe run',
  measureButton: 'Run probe live',
  measuring: (elapsed) => `Running… (${elapsed})`,
  measureHint:
    'This sends up to 48 real requests to models (at most 4 calls per each of the 12 cheapest models) and costs real money — the exact amount depends on each model’s live price and cannot be stated in advance.',
  confirmRun: 'This sends up to 48 live requests to models and costs real money (amount unknown, depends on each model’s live price). Continue?',
  lastSaved: (date, time) => `Last saved: ${date} — ${time}`,

  elapsedSeconds: (n) => `${n} seconds`,
  elapsedMinutes: (n) => `${n} minutes`,
  elapsedMinutesSeconds: (m, s) => `${m} minutes ${s} seconds`,

  measureFailedToast: 'The probe run failed',
  measureDone: (measured, eligible) => `Probe finished — out of ${measured} models scanned, ${eligible} qualified as routers`,
  loadErrorToast: 'Failed to load the router probe result',
  retry: 'Retry',

  staleWarning: (date, time) =>
    `This result is from ${date} — ${time}, over 7 days old. The smart router still honours this old result as-is — re-run the probe before trusting this table.`,
  measuredAt: (date, time) => `Last probe run: ${date} — ${time}`,

  statEligible: 'Eligible as router',
  statPermanent: 'Permanently unsuitable',
  statTransient: 'Unknown — transient failure',

  neverMeasuredTitle: 'This probe has never been run.',
  neverMeasuredBody:
    'That means no model has been checked for "being a router" yet — not that all of them failed. Click "Run probe live" to fill this table.',
  loading: 'Loading…',
  noData: 'No data available',

  colModel: 'Model public ID',
  colState: 'State',
  colReason: 'Reason',
  colRetryAfter: 'Retry after',
  colLastRecorded: 'Last recorded',

  stateEligible: 'Eligible',
  stateIneligiblePermanent: 'Not eligible (permanent)',
  stateIneligibleTransient: 'Unknown (transient)',

  reasonBadShape: 'Malformed reply — the model did not give an acceptable answer to the synthetic menu.',
  reasonNoDiscrimination: "Doesn't tell a greeting apart from a reasoning message.",
  reasonProviderNotConfigured: "This model's provider is not currently configured.",
  reasonTransientTimeout: 'The upstream did not answer in time — this is a transient failure, not a verdict on the model.',
  reasonTransientException: 'A transient connection error to the upstream — not a verdict on the model.',
  reasonTransientHttp: (code) => `The upstream returned HTTP ${code} — a known transient blip, not a verdict on the model.`,
  reasonUnknown: (raw) => `Recorded reason: ${raw}`,
  sampleReplyLabel: 'Recorded sample reply',
  noReason: '—',
  noRetry: '—',
}

export const routerProbeStrings = dict(FA, EN)
