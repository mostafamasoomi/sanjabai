import { dict } from '@/lib/i18n'

/* Sibling to page.tsx. See lib/i18n.ts for why `EN: typeof FA` (and the
   absence of `as const` on FA) is what makes a missing key a build error. */

const FA = {
  title: 'بازنشانی رمز عبور',
  emailRequired: 'ایمیل خود را وارد کنید',
  sentToast: 'لینک بازنشانی رمز عبور به ایمیل شما ارسال شد',
  genericError: 'خطا در ارسال ایمیل',
  networkError: 'خطا در ارتباط با سرور',
  sentPrefix: 'ایمیل بازنشانی رمز عبور به',
  sentSuffix: 'ارسال شد. لطفاً صندوق ورودی خود را بررسی کنید.',
  backToLogin: 'بازگشت به ورود',
  intro: 'ایمیل خود را وارد کنید تا لینک بازنشانی رمز عبور برای شما ارسال شود.',
  emailLabel: 'ایمیل',
  submitBusy: 'در حال ارسال...',
  submit: 'ارسال لینک بازنشانی',
}

const EN: typeof FA = {
  title: 'Reset your password',
  emailRequired: 'Enter your email',
  sentToast: 'A password reset link has been sent to your email',
  genericError: 'Failed to send the email',
  networkError: 'Failed to connect to the server',
  sentPrefix: 'A password reset email was sent to',
  sentSuffix: 'Please check your inbox.',
  backToLogin: 'Back to sign in',
  intro: 'Enter your email and we’ll send you a password reset link.',
  emailLabel: 'Email',
  submitBusy: 'Sending...',
  submit: 'Send reset link',
}

export const forgotPasswordPageStrings = dict(FA, EN)
