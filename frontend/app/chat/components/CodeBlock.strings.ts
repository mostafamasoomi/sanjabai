import { dict } from '@/lib/i18n'

const FA = {
  copy: 'کپی',
  copied: 'کپی شد',
  copyCode: 'کپی کد',
}

const EN: typeof FA = {
  copy: 'Copy',
  copied: 'Copied',
  copyCode: 'Copy code',
}

export const codeBlockStrings = dict(FA, EN)
