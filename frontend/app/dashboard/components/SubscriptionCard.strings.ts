import { dict } from '@/lib/i18n'

const FA = {
  status: 'وضعیت اشتراک',
  tokensUsed: 'توکن مصرف شده',
  endsAt: (date: string) => `تاریخ پایان: ${date}`,
  changePlan: 'تغییر پلن',
}

const EN: typeof FA = {
  status: 'Subscription status',
  tokensUsed: 'Tokens used',
  endsAt: (date) => `Ends: ${date}`,
  changePlan: 'Change plan',
}

export const subscriptionCardStrings = dict(FA, EN)
