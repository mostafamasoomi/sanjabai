import { dict } from '@/lib/i18n'

const FA = {
  title: 'تنظیمات پروکسی',
  subtitle: 'مدیریت تونل و پروکسی اتصال',
  loadError: 'خطا در دریافت تنظیمات پروکسی',
  saveSuccess: 'تنظیمات پروکسی ذخیره شد',
  saveError: 'خطا در ذخیره پروکسی',
  tunnelActive: 'تونل فعال است',
  tunnelInactive: 'تونل غیرفعال است',
  proxyType: 'نوع پروکسی',
  proxyUrl: 'آدرس پروکسی',
  status: 'وضعیت',
  active: 'فعال',
  disabled: 'غیرفعال',
  saveApply: 'ذخیره و اعمال',
}

const EN: typeof FA = {
  title: 'Proxy settings',
  subtitle: 'Manage the connection tunnel and proxy',
  loadError: 'Failed to load proxy settings',
  saveSuccess: 'Proxy settings saved',
  saveError: 'Failed to save proxy settings',
  tunnelActive: 'Tunnel is active',
  tunnelInactive: 'Tunnel is inactive',
  proxyType: 'Proxy type',
  proxyUrl: 'Proxy address',
  status: 'Status',
  active: 'Active',
  disabled: 'Disabled',
  saveApply: 'Save and apply',
}

export const proxyStrings = dict(FA, EN)
