import { dict } from '@/lib/i18n'

const FA = {
  title: 'دسترسی سریع',
  chatLabel: 'شروع مکالمه',
  chatDesc: 'گفتگو با هوش مصنوعی',
  walletLabel: 'کیف پول',
  walletDesc: 'شارژ و مدیریت حساب',
  modelsLabel: 'مدل‌ها',
  modelsDesc: (n: string) => `${n} مدل در دسترس`,
  creditLabel: 'خرید بسته اعتباری',
  creditDesc: 'خرید بسته اعتباری ویژه',
  billingLabel: 'تنظیمات صورتحساب',
  billingDesc: 'مدیریت پرداخت به ازای مصرف',
}

const EN: typeof FA = {
  title: 'Quick actions',
  chatLabel: 'Start a conversation',
  chatDesc: 'Chat with the AI',
  walletLabel: 'Wallet',
  walletDesc: 'Top up and manage your account',
  modelsLabel: 'Models',
  modelsDesc: (n) => `${n} models available`,
  creditLabel: 'Buy a credit package',
  creditDesc: 'Buy a special credit package',
  billingLabel: 'Billing settings',
  billingDesc: 'Manage pay-as-you-go',
}

export const quickActionsCardStrings = dict(FA, EN)
