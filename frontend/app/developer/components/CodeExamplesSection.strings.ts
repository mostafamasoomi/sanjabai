import { dict } from '@/lib/i18n'

const FA = {
  title: 'نمونه کد',
  installLabel: 'نصب وابستگی:',
  copied: 'کپی شد',
  copy: 'کپی',
}

const EN: typeof FA = {
  title: 'Code samples',
  installLabel: 'Install:',
  copied: 'Copied',
  copy: 'Copy',
}

export const codeExamplesSectionStrings = dict(FA, EN)
