import { dict } from '@/lib/i18n'

const FA = {
  user: 'کاربر',
  memberSince: (date: string) => `عضو از ${date}`,
  balance: 'موجودی',
  monthlyUsage: 'مصرف ماهانه',
  tokens: (n: string) => `${n} توکن`,
  email: 'ایمیل',
  statsError: 'خطا در بارگذاری موجودی و آمار مصرف.',
}

const EN: typeof FA = {
  user: 'User',
  memberSince: (date) => `Member since ${date}`,
  balance: 'Balance',
  monthlyUsage: 'Monthly usage',
  tokens: (n) => `${n} tokens`,
  email: 'Email',
  statsError: 'Failed to load balance and usage stats.',
}

export const profileAvatarCardStrings = dict(FA, EN)
