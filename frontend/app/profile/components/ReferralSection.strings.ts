import { dict } from '@/lib/i18n'

const FA = {
  title: 'دعوت دوستان',
  intro: 'لینک دعوت خود را با دوستانتان به اشتراک بگذارید تا با نام شما در Sanjabai ثبت‌نام کنند.',
  yourCode: 'کد دعوت شما',
  codeCopied: 'کد کپی شد',
  copy: 'کپی',
  yourLink: 'لینک دعوت',
  linkCopied: 'لینک کپی شد',
}

const EN: typeof FA = {
  title: 'Invite Friends',
  intro: 'Share your invite link so friends sign up to Sanjabai through you.',
  yourCode: 'Your Referral Code',
  codeCopied: 'Code copied',
  copy: 'Copy',
  yourLink: 'Referral Link',
  linkCopied: 'Link copied',
}

export const referralSectionStrings = dict(FA, EN)
