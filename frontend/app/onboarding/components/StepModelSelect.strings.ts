import { dict } from '@/lib/i18n'

const FA = {
  title: 'مدل‌های موردعلاقه شما',
  subtitle: 'از بین مدل‌های موجود، ۲ تا ۳ مدل موردعلاقه‌تان را انتخاب کنید.',
  noModels: 'در حال حاضر مدلی در دسترس نیست.',
  selectedCount: (n: string) => `${n} مدل انتخاب شده`,
  back: 'قبلی',
  next: 'ادامه',
}

const EN: typeof FA = {
  title: 'Your favorite models',
  subtitle: 'Pick 2-3 favorite models from what is available.',
  noModels: 'No models are available right now.',
  selectedCount: (n) => `${n} model${n === '1' ? '' : 's'} selected`,
  back: 'Back',
  next: 'Continue',
}

export const stepModelSelectStrings = dict(FA, EN)
