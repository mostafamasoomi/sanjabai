import { dict } from '@/lib/i18n'

const FA = {
  title: 'داشبورد',
  subtitle: 'نمای کلی کاربران، درآمد و مصرف',
  loadError: 'خطا در دریافت آمار داشبورد',
  totalUsers: 'کل کاربران',
  activeUsers: 'کاربران فعال',
  totalRevenue: 'درآمد کل',
  tokensUsed: 'توکن مصرفی',
  conversations: 'گفتگوها',
  zeroPrice: '۰ تومان',
  zeroCount: '۰',
  recentTransactions: 'تراکنش‌های اخیر',
  colUserId: 'شناسه کاربر',
  colAmount: 'مبلغ',
  colDescription: 'شرح',
  colDate: 'تاریخ',
  noTransactions: 'تراکنشی ثبت نشده',
}

const EN: typeof FA = {
  title: 'Dashboard',
  subtitle: 'Overview of users, revenue and usage',
  loadError: 'Failed to load dashboard stats',
  totalUsers: 'Total users',
  activeUsers: 'Active users',
  totalRevenue: 'Total revenue',
  tokensUsed: 'Tokens used',
  conversations: 'Conversations',
  zeroPrice: '0 Toman',
  zeroCount: '0',
  recentTransactions: 'Recent transactions',
  colUserId: 'User ID',
  colAmount: 'Amount',
  colDescription: 'Description',
  colDate: 'Date',
  noTransactions: 'No transactions recorded',
}

export const dashboardStrings = dict(FA, EN)
