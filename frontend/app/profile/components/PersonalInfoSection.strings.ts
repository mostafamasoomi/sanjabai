import { dict } from '@/lib/i18n'

const FA = {
  title: 'اطلاعات شخصی',
  displayName: 'نام نمایشی',
  displayNamePlaceholder: 'نام شما',
  bio: 'بیوگرافی',
  bioPlaceholder: 'درباره خودتان بنویسید...',
  timezone: 'منطقه زمانی',
}

const EN: typeof FA = {
  title: 'Personal Info',
  displayName: 'Display Name',
  displayNamePlaceholder: 'Your name',
  bio: 'Bio',
  bioPlaceholder: 'Tell us about yourself...',
  timezone: 'Timezone',
}

export const personalInfoSectionStrings = dict(FA, EN)
