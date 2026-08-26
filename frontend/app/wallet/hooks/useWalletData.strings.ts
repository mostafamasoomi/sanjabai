import { dict } from '@/lib/i18n'

const FA = {
  fetchError: 'خطا در دریافت اطلاعات',
}

const EN: typeof FA = {
  fetchError: 'Failed to load data',
}

export const useWalletDataStrings = dict(FA, EN)
