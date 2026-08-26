import { dict } from '@/lib/i18n'

const FA = {
  fetchError: 'خطا در دریافت اطلاعات مصرف',
  serverError: 'خطا در ارتباط با سرور',
  csvFetchError: 'خطا در دریافت فایل CSV',
  csvDownloaded: 'فایل CSV دانلود شد',
}

const EN: typeof FA = {
  fetchError: 'Error loading usage data',
  serverError: 'Error connecting to the server',
  csvFetchError: 'Error downloading the CSV file',
  csvDownloaded: 'CSV file downloaded',
}

export const useUsageDataStrings = dict(FA, EN)
