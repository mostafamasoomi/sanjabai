import { dict } from '@/lib/i18n'

const FA = {
  copyLabel: 'کپی کردن نمونه کد',
  copiedLabel: 'کپی شد',
  eyebrow: 'برای توسعه‌دهندگان',
  title: 'یک endpoint، همه‌ی مدل‌ها',
  // Split around the base-URL span so it can keep its own `lp-latin` styling
  // without the sentence being reassembled from fragments at the call site.
  leadBefore: 'آدرس پایه را به ',
  leadAfter: ' تغییر دهید. همین. کتابخانه‌های رسمی OpenAI بدون هیچ تغییر دیگری کار می‌کنند.',
  codeTabAria: 'زبان نمونه کد',
  docsLinkLabel: 'مطالعه‌ی مستندات',
}

const EN: typeof FA = {
  copyLabel: 'Copy sample code',
  copiedLabel: 'Copied',
  eyebrow: 'For developers',
  title: 'One endpoint, every model',
  leadBefore: 'Change the base URL to ',
  leadAfter: ". That's it — the official OpenAI libraries work with no other change.",
  codeTabAria: 'Sample code language',
  docsLinkLabel: 'Read the docs',
}

export const apiSectionStrings = dict(FA, EN)
