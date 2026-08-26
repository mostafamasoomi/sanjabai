import { dict } from '@/lib/i18n'

const FA = {
  title: 'گران‌ترین درخواست اخیر',
  tokens: (input: string, output: string) => `${input} ورودی / ${output} خروجی`,
}

const EN: typeof FA = {
  title: 'Most expensive recent call',
  tokens: (input, output) => `${input} in / ${output} out`,
}

export const mostExpensiveCardStrings = dict(FA, EN)
