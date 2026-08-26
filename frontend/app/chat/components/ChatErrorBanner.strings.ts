import { dict } from '@/lib/i18n'

const FA = {
  balanceTitle: 'اعتبار شما تمام شده!',
  balanceBody: 'برای ادامه استفاده از مدل‌های هوش مصنوعی، نیاز به شارژ حساب دارید.',
  balanceBody2: 'با شارژ حساب می‌توانید بدون محدودیت از تمام مدل‌ها استفاده کنید.',
  viewPlans: 'مشاهده پلن‌ها و شارژ حساب',
  wallet: 'کیف پول',
}

const EN: typeof FA = {
  balanceTitle: 'Your balance has run out!',
  balanceBody: 'To keep using the AI models, you need to top up your account.',
  balanceBody2: 'Once topped up, you can use every model without limits.',
  viewPlans: 'View plans and top up',
  wallet: 'Wallet',
}

export const chatErrorBannerStrings = dict(FA, EN)
