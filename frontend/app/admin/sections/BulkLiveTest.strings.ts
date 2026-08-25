import { dict } from '@/lib/adminI18n'

const FA = {
  selectAtLeastOne: 'ابتدا حداقل یک مدل را انتخاب کنید',
  confirmBulk: (count: string, minutes: string) =>
    `${count} مدل انتخاب شده است. تست زندهٔ همهٔ آن‌ها حدود ${minutes} دقیقه طول می‌کشد `
    + 'و در همین صفحه اجرا می‌شود (با بستن صفحه متوقف می‌شود). ادامه می‌دهید؟',
  networkError: 'خطای شبکه',
  stopped: (ok: string, done: string) => `تست متوقف شد — ${ok} مدل سالم از ${done} مدل آزموده‌شده`,
  finished: (ok: string, total: string) => `${ok} مدل از ${total} مدل سالم بود`,
  progress: (done: string, total: string, ok: string) => `در حال تست زنده: ${done} از ${total} — ${ok} مدل سالم`,
  stop: 'توقف',
}

const EN: typeof FA = {
  selectAtLeastOne: 'Select at least one model first',
  confirmBulk: (count, minutes) =>
    `${count} models selected. Live-testing all of them will take about ${minutes} minutes `
    + 'and runs on this page (closing it stops the run). Continue?',
  networkError: 'Network error',
  stopped: (ok, done) => `Test stopped — ${ok} of ${done} tested models were healthy`,
  finished: (ok, total) => `${ok} of ${total} models were healthy`,
  progress: (done, total, ok) => `Running live test: ${done} of ${total} — ${ok} healthy`,
  stop: 'Stop',
}

export const bulkLiveTestStrings = dict(FA, EN)
