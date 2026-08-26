import { dict } from '@/lib/i18n'

const FA = {
  title: 'کلیدهای API',
  namePlaceholder: 'نام کلید (مثلاً Development)',
  create: 'ساخت کلید',
  emptyTitle: 'هنوز کلیدی نساخته‌اید',
  emptyDesc: 'اولین کلید API خود را بسازید.',
  active: 'فعال',
  inactive: 'غیرفعال',
  rotateTitle: 'چرخاندن کلید (ساخت رمز جدید)',
  revokeTitle: 'غیرفعال کردن',
}

const EN: typeof FA = {
  title: 'API keys',
  namePlaceholder: 'Key name (e.g. Development)',
  create: 'Create key',
  emptyTitle: 'You haven’t created a key yet',
  emptyDesc: 'Create your first API key.',
  active: 'Active',
  inactive: 'Inactive',
  rotateTitle: 'Rotate key (generate a new secret)',
  revokeTitle: 'Disable',
}

export const apiKeysSectionStrings = dict(FA, EN)
