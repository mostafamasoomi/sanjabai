import { dict } from '@/lib/i18n'

const FA = {
  title: 'قصد دارید چه کاری کنید؟',
  subtitle: 'بر اساس انتخاب شما، بهترین مدل را پیشنهاد می‌دهیم.',
  back: 'قبلی',
  next: 'ادامه',
}

const EN: typeof FA = {
  title: 'What do you want to do?',
  subtitle: "We'll suggest the best model based on your choice.",
  back: 'Back',
  next: 'Continue',
}

export const stepGoalStrings = dict(FA, EN)
