import { dict } from '@/lib/i18n'

const FA = {
  title: 'اطلاعات حساب',
  email: 'ایمیل',
  username: 'نام کاربری',
  phone: 'تلفن',
  status: 'وضعیت',
  joined: 'تاریخ عضویت',
  active: 'فعال',
  inactive: 'غیرفعال',
  manage: 'مدیریت حساب',
}

const EN: typeof FA = {
  title: 'Account info',
  email: 'Email',
  username: 'Username',
  phone: 'Phone',
  status: 'Status',
  joined: 'Joined',
  active: 'Active',
  inactive: 'Inactive',
  manage: 'Manage account',
}

export const accountInfoCardStrings = dict(FA, EN)
