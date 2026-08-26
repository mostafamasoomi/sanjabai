import { dict } from '@/lib/i18n'

const FA = {
  title: 'کدهای تخفیف',
  subtitle: (n: string) => `${n} کد تخفیف ثبت شده`,
  loadError: 'خطا در دریافت کدهای تخفیف',
  noneRegistered: 'کد تخفیفی ثبت نشده',
  active: 'فعال',
  disabled: 'غیرفعال',
  editTitle: 'ویرایش کد تخفیف',
  addTitle: 'افزودن کد تخفیف',
  codeField: 'کد تخفیف',
  percentField: 'درصد تخفیف',
  statusField: 'وضعیت',
  update: 'بروزرسانی',
  add: 'افزودن',
  cancel: 'انصراف',
  saveEditSuccess: 'تخفیف ویرایش شد',
  saveAddSuccess: 'تخفیف اضافه شد',
  saveError: 'خطا در ذخیره تخفیف',
  deleteSuccess: 'تخفیف حذف شد',
  deleteError: 'خطا در حذف تخفیف',
}

const EN: typeof FA = {
  title: 'Discount codes',
  subtitle: (n) => `${n} discount code${n === '1' ? '' : 's'} registered`,
  loadError: 'Failed to load discount codes',
  noneRegistered: 'No discount codes registered',
  active: 'Active',
  disabled: 'Disabled',
  editTitle: 'Edit discount code',
  addTitle: 'Add discount code',
  codeField: 'Discount code',
  percentField: 'Discount percentage',
  statusField: 'Status',
  update: 'Update',
  add: 'Add',
  cancel: 'Cancel',
  saveEditSuccess: 'Discount updated',
  saveAddSuccess: 'Discount added',
  saveError: 'Failed to save discount',
  deleteSuccess: 'Discount deleted',
  deleteError: 'Failed to delete discount',
}

export const discountsStrings = dict(FA, EN)
