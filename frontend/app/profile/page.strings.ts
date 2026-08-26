import { dict } from '@/lib/i18n'

const FA = {
  title: 'پروفایل کاربری',
  saveChanges: 'ذخیره تغییرات',
}

const EN: typeof FA = {
  title: 'User Profile',
  saveChanges: 'Save Changes',
}

export const profilePageStrings = dict(FA, EN)
