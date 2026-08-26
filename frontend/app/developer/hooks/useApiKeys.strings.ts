import { dict } from '@/lib/i18n'

const FA = {
  fetchError: 'خطا در دریافت کلیدهای API',
  serverError: 'خطا در ارتباط با سرور',
  nameRequired: 'نام کلید را وارد کنید',
  genericError: 'خطا',
  connectionError: 'خطا در ارتباط',
  rotateConfirm: 'با چرخاندن این کلید، کلید فعلی بلافاصله از کار می‌افتد و باید کلید جدید را در همه جا جایگزین کنید. ادامه می‌دهید؟',
  revokeConfirm: 'آیا از غیرفعال کردن این کلید مطمئن هستید؟',
  revoked: 'کلید غیرفعال شد',
}

const EN: typeof FA = {
  fetchError: 'Error loading API keys',
  serverError: 'Error connecting to the server',
  nameRequired: 'Enter a name for the key',
  genericError: 'Error',
  connectionError: 'Connection error',
  rotateConfirm: 'Rotating this key immediately disables the current one — you’ll need to replace it everywhere it’s used. Continue?',
  revokeConfirm: 'Are you sure you want to disable this key?',
  revoked: 'Key disabled',
}

export const useApiKeysStrings = dict(FA, EN)
