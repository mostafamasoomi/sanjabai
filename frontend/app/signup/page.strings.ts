import { dict } from '@/lib/i18n'

/* Sibling to page.tsx. See lib/i18n.ts for why `EN: typeof FA` (and the
   absence of `as const` on FA) is what makes a missing key a build error. */

const FA = {
  title: 'ثبت‌نام در Sanjabai',
  subtitle: 'دسترسی به همه مدل‌های هوش مصنوعی',
  emailLabel: 'ایمیل',
  passwordLabel: 'رمز عبور',
  passwordPlaceholder: 'حداقل ۸ کاراکتر',
  password2Label: 'تکرار رمز عبور',
  password2Placeholder: 'رمز عبور را دوباره وارد کنید',
  emailInvalid: 'ایمیل معتبر وارد کنید',
  passwordTooShort: 'رمز عبور حداقل ۸ کاراکتر باشد',
  passwordsMismatch: 'رمزهای عبور یکسان نیستند',
  passwordsMatch: 'مطابقت دارد',
  captchaLabel: 'کپچا',
  captchaPlaceholder: 'پاسخ را وارد کنید',
  captchaRefresh: 'تصویر جدید',
  submitBusy: 'در حال ثبت‌نام...',
  submit: 'ثبت‌نام',
  haveAccount: 'قبلاً ثبت‌نام کرده‌اید؟',
  login: 'ورود',
  trustSsl: 'رمزنگاری SSL',
  trustNoVpn: 'بدون نیاز به VPN',
  trustTomanTopUp: 'شارژ ریالی',
  errMissingFields: 'ایمیل و رمز عبور را وارد کنید',
  errEmailInvalid: 'ایمیل معتبر وارد کنید',
  errPasswordTooShort: 'رمز عبور حداقل ۸ کاراکتر باشد',
  errPasswordsMismatch: 'رمزهای عبور یکسان نیستند',
  errCaptchaRequired: 'پاسخ کپچا را وارد کنید',
  errSignupFailed: 'خطا در ثبت‌نام',
  // Shown only when the URL carries ?ref=. Deliberately promises no amount:
  // the reward seeds at zero and pays out after the invitee's first
  // successful top-up, never at signup (services/referral.py).
  referralBanner: 'با دعوت یک دوست وارد می‌شوید.',
}

const EN: typeof FA = {
  title: 'Sign up for Sanjabai',
  subtitle: 'Access every AI model',
  emailLabel: 'Email',
  passwordLabel: 'Password',
  passwordPlaceholder: 'At least 8 characters',
  password2Label: 'Confirm password',
  password2Placeholder: 'Enter your password again',
  emailInvalid: 'Enter a valid email',
  passwordTooShort: 'Password must be at least 8 characters',
  passwordsMismatch: 'Passwords don’t match',
  passwordsMatch: 'Matches',
  captchaLabel: 'Captcha',
  captchaPlaceholder: 'Enter the answer',
  captchaRefresh: 'New image',
  submitBusy: 'Signing up...',
  submit: 'Sign up',
  haveAccount: 'Already have an account?',
  login: 'Sign in',
  trustSsl: 'SSL encryption',
  trustNoVpn: 'No VPN required',
  trustTomanTopUp: 'Toman top-up',
  errMissingFields: 'Enter your email and password',
  errEmailInvalid: 'Enter a valid email',
  errPasswordTooShort: 'Password must be at least 8 characters',
  errPasswordsMismatch: 'Passwords don’t match',
  errCaptchaRequired: 'Enter the captcha answer',
  errSignupFailed: 'Sign up failed',
  referralBanner: "You're signing up from a friend's invite.",
}

export const signupPageStrings = dict(FA, EN)
