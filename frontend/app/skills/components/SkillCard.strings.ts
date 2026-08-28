import { dict } from '@/lib/i18n'

const FA = {
  usageCount: (n: string) => `${n} استفاده`,
  useAction: 'استفاده',
  useOnceHint: 'یک‌بار اجرا می‌شود — برای اینکه همیشه فعال باشد، از «مهارت‌های فعال» بالای صفحه استفاده کنید.',
}

const EN: typeof FA = {
  usageCount: (n) => `${n} uses`,
  useAction: 'Use',
  useOnceHint: 'Runs once — to keep it always on, use "Active skills" at the top of the page.',
}

export const skillCardStrings = dict(FA, EN)
