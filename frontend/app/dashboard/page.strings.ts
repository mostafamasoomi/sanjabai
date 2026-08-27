import { dict } from '@/lib/i18n'

/* Dashboard page: header, stat-card labels/units, and the plan badge labels
   this page derives locally from the user's profile (`profile.plan`) for
   the header badge -- unrelated to the retired subscription concept. */

const FA = {
  greeting: (name: string) => `سلام، ${name}`,
  subtitle: 'خوش آمدید به داشبورد مولتیای',
  defaultUser: 'کاربر',
  refresh: 'بروزرسانی',
  statBalance: 'موجودی کیف پول',
  statSpent: 'کل هزینه',
  statConversations: 'تعداد مکالمات',
  statTokens: 'کل توکن‌ها',
  unitToman: 'تومان',
  unitConversation: 'مکالمه',
  unitToken: 'توکن',
  planLabels: {
    free: 'رایگان',
    pro: 'حرفه‌ای',
    enterprise: 'سازمانی',
  } as Record<string, string>,
}

const EN: typeof FA = {
  greeting: (name) => `Hi, ${name}`,
  subtitle: 'Welcome to your Sanjabai dashboard',
  defaultUser: 'User',
  refresh: 'Refresh',
  statBalance: 'Wallet balance',
  statSpent: 'Total spent',
  statConversations: 'Conversations',
  statTokens: 'Total tokens',
  unitToman: 'Toman',
  unitConversation: 'conversations',
  unitToken: 'tokens',
  planLabels: {
    free: 'Free',
    pro: 'Pro',
    enterprise: 'Enterprise',
  },
}

export const dashboardPageStrings = dict(FA, EN)
