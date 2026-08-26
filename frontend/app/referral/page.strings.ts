import { dict } from '@/lib/i18n'

/* Sibling to page.tsx. See lib/i18n.ts for why `EN: typeof FA` (and the
   absence of `as const` on FA) is what makes a missing key a build error. */

const FA = {
  title: 'دعوت از دوستان',
  subtitle: 'دوستان خود را با لینک اختصاصی خود به Sanjabai دعوت کنید',
  yourCode: 'کد دعوت شما',
  loading: 'در حال بارگذاری...',
  copy: 'کپی',
  howItWorks: 'نحوه کار',
  step1: 'لینک دعوت خود را با دوستان به اشتراک بگذارید',
  step2: 'دوست شما با این لینک در Sanjabai ثبت‌نام می‌کند',
}

const EN: typeof FA = {
  title: 'Invite friends',
  subtitle: 'Invite your friends to Sanjabai with your own referral link',
  yourCode: 'Your referral code',
  loading: 'Loading...',
  copy: 'Copy',
  howItWorks: 'How it works',
  step1: 'Share your invite link with friends',
  step2: 'Your friend signs up for Sanjabai with that link',
}

export const referralPageStrings = dict(FA, EN)
