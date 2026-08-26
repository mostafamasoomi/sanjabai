import { dict } from '@/lib/i18n'

/* Sibling to page.tsx. See lib/i18n.ts for why `EN: typeof FA` (and the
   absence of `as const` on FA) is what makes a missing key a build error. */

const FA = {
  title: 'ورود به حساب',
  subtitle: 'به Sanjabai خوش آمدید',
  emailLabel: 'ایمیل',
  passwordLabel: 'رمز عبور',
  passwordPlaceholder: 'حداقل ۸ کاراکتر',
  captchaLabel: 'کپچا',
  captchaPlaceholder: 'پاسخ را وارد کنید',
  captchaRefresh: 'تصویر جدید',
  submitBusy: 'در حال ورود...',
  submit: 'ورود',
  forgotPassword: 'رمز عبور را فراموش کرده‌اید؟',
  noAccount: 'حساب کاربری ندارید؟',
  signup: 'ثبت‌نام',
  trustSecure: 'امن',
  trustNoVpn: 'بدون VPN',
  errMissingFields: 'ایمیل و رمز عبور را وارد کنید',
  errCaptchaRequired: 'پاسخ کپچا را وارد کنید',
  errLoginFailed: 'خطا در ورود',
}

const EN: typeof FA = {
  title: 'Sign in to your account',
  subtitle: 'Welcome to Sanjabai',
  emailLabel: 'Email',
  passwordLabel: 'Password',
  passwordPlaceholder: 'At least 8 characters',
  captchaLabel: 'Captcha',
  captchaPlaceholder: 'Enter the answer',
  captchaRefresh: 'New image',
  submitBusy: 'Signing in...',
  submit: 'Sign in',
  forgotPassword: 'Forgot your password?',
  noAccount: 'Don’t have an account?',
  signup: 'Sign up',
  trustSecure: 'Secure',
  trustNoVpn: 'No VPN',
  errMissingFields: 'Enter your email and password',
  errCaptchaRequired: 'Enter the captcha answer',
  errLoginFailed: 'Sign in failed',
}

export const loginPageStrings = dict(FA, EN)
