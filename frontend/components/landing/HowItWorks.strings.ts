import { dict } from '@/lib/i18n'

const FA = {
  eyebrow: 'شروع کار',
  title: 'در سه قدم راه بیفتید',
}

const EN: typeof FA = {
  eyebrow: 'Getting started',
  title: 'Up and running in three steps',
}

export const howItWorksStrings = dict(FA, EN)
