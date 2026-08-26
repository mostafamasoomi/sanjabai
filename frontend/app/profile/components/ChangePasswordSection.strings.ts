import { dict } from '@/lib/i18n'

const FA = {
  title: 'تغییر رمز عبور',
  current: 'رمز عبور فعلی',
  currentPlaceholder: 'رمز عبور فعلی',
  newPassword: 'رمز عبور جدید',
  newPasswordPlaceholder: 'حداقل ۸ کاراکتر',
  confirm: 'تکرار رمز عبور جدید',
  confirmPlaceholder: 'تکرار رمز عبور جدید',
  submit: 'تغییر رمز عبور',
}

const EN: typeof FA = {
  title: 'Change Password',
  current: 'Current Password',
  currentPlaceholder: 'Current password',
  newPassword: 'New Password',
  newPasswordPlaceholder: 'At least 8 characters',
  confirm: 'Confirm New Password',
  confirmPlaceholder: 'Confirm new password',
  submit: 'Change Password',
}

export const changePasswordSectionStrings = dict(FA, EN)
