import { dict } from '@/lib/i18n'

const FA = {
  closeAria: 'بستن',
  usageCount: (n: string) => `${n} استفاده`,
  modelLabel: 'مدل',
  modelPlaceholder: 'نام مدل (مثلاً gpt-4)',
  variablesLabel: 'متغیرها',
  runningText: 'در حال اجرا...',
  runAction: 'اجرا',
  outputLabel: 'خروجی',
  copyAction: 'کپی',
  copiedToast: 'کپی شد',
  modelResultLabel: (model: string) => `مدل: ${model}`,
  yourRating: 'امتیاز شما:',
  starAria: (n: number) => `${n} ستاره`,
  toastUseError: 'خطا در اجرای مهارت',
  toastServerError: 'خطا در ارتباط با سرور',
  toastRateSuccess: 'امتیاز شما ثبت شد',
  toastRateError: 'خطا در ثبت امتیاز',
}

const EN: typeof FA = {
  closeAria: 'Close',
  usageCount: (n) => `${n} uses`,
  modelLabel: 'Model',
  modelPlaceholder: 'Model name (e.g. gpt-4)',
  variablesLabel: 'Variables',
  runningText: 'Running...',
  runAction: 'Run',
  outputLabel: 'Output',
  copyAction: 'Copy',
  copiedToast: 'Copied',
  modelResultLabel: (model) => `Model: ${model}`,
  yourRating: 'Your rating:',
  starAria: (n) => `${n} stars`,
  toastUseError: 'Failed to run skill',
  toastServerError: 'Server connection error',
  toastRateSuccess: 'Your rating was saved',
  toastRateError: 'Failed to save rating',
}

export const useSkillModalStrings = dict(FA, EN)
