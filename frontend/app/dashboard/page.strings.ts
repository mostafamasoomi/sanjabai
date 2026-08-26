import { dict } from '@/lib/i18n'

/* Dashboard page: header, stat-card labels/units, and the plan/subscription
   labels this page derives locally (name_fa/name_en, where present, comes
   straight from the backend -- see the note at the call site). */

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
  subStatus: {
    active: 'فعال',
    cancelled: 'لغو شده',
    none: 'بدون اشتراک',
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
  subStatus: {
    active: 'Active',
    cancelled: 'Cancelled',
    none: 'No subscription',
  },
}

export const dashboardPageStrings = dict(FA, EN)
