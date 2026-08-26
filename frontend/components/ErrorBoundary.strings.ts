import { dict } from '@/lib/i18n'

const FA = {
  loadError: 'خطا در بارگذاری',
  genericProblem: 'مشکلی در این بخش پیش آمده',
  retry: 'تلاش مجدد',
}

const EN: typeof FA = {
  loadError: 'Failed to load',
  genericProblem: 'Something went wrong in this section',
  retry: 'Retry',
}

export const errorBoundaryStrings = dict(FA, EN)
