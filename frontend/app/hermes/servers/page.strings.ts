import { dict } from '@/lib/i18n'

const FA = {
  loadError: 'خطا در دریافت سرورها',
  signIn: 'وارد شوید',
  loginToAccount: 'ورود به حساب',
  pageTitle: 'سرورهای هرمس من',
  newServer: 'سرور جدید',
  emptyTitle: 'هنوز سروری ندارید',
  emptyDescription: 'یک سرور هرمس سفارش دهید تا اینجا نمایش داده شود.',
  viewPlans: 'مشاهده پلن‌ها',
  serverNumber: (id: string) => `سرور #${id}`,
  inSync: 'همگام',
  syncing: 'در حال اعمال تغییرات',
  perMonth: (price: string) => `${price}/ماه`,
  status: {
    provisioning: 'در حال راه‌اندازی',
    active: 'فعال',
    suspended: 'متوقف‌شده',
    terminated: 'خاتمه‌یافته',
  },
}

const EN: typeof FA = {
  loadError: 'Failed to load servers',
  signIn: 'Sign in',
  loginToAccount: 'Sign in to your account',
  pageTitle: 'My Hermes servers',
  newServer: 'New server',
  emptyTitle: 'No servers yet',
  emptyDescription: 'Order a Hermes server to see it here.',
  viewPlans: 'View plans',
  serverNumber: (id) => `Server #${id}`,
  inSync: 'In sync',
  syncing: 'Applying changes',
  perMonth: (price) => `${price}/mo`,
  status: {
    provisioning: 'Provisioning',
    active: 'Active',
    suspended: 'Suspended',
    terminated: 'Terminated',
  },
}

export const hermesServersStrings = dict(FA, EN)
