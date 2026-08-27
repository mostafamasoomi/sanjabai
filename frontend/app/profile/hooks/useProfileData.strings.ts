import { dict } from '@/lib/i18n'

/* Toasts from useProfileData.ts. These used to be keyed off the account's
   own stored `language` preference (`language === 'fa' ? … : …`), a field
   distinct from the site-wide UI language (`useLang()`/the header toggle) --
   see the file-level comment in useProfileData.ts for why they now follow
   the UI language instead. */

const FA = {
  profileSaved: 'پروفایل با موفقیت ذخیره شد',
  profileSaveError: 'خطا در ذخیره پروفایل',
  serverError: 'خطا در ارتباط با سرور',
  fileTooLarge: 'حجم فایل نباید بیشتر از ۱ مگابایت باشد',
  fileLoaded: 'فایل بارگذاری شد — برای ذخیره، «ذخیره تغییرات» را بزنید',
  fileReadError: 'خطا در خواندن فایل',
  imageTooLarge: 'حجم تصویر نباید بیشتر از ۲ مگابایت باشد',
  invalidImageType: 'فرمت تصویر پشتیبانی نمی‌شود. فرمت‌های مجاز: JPG، PNG، WEBP، GIF',
  avatarUpdated: 'تصویر پروفایل بروزرسانی شد',
  avatarUploadError: 'خطا در آپلود تصویر',
  removeAvatarConfirm: 'آیا از حذف تصویر پروفایل مطمئن هستید؟',
  avatarRemoved: 'تصویر پروفایل حذف شد',
  avatarRemoveError: 'خطا در حذف تصویر پروفایل',
  passwordMismatch: 'رمز عبور جدید با تکرار آن مطابقت ندارد',
  passwordTooShort: 'رمز عبور باید حداقل ۸ کاراکتر باشد',
  passwordChanged: 'رمز عبور با موفقیت تغییر کرد',
  passwordChangeError: 'خطا در تغییر رمز عبور',
  enterTelegramId: 'شناسه تلگرام را وارد کنید',
  telegramIdInvalid: 'شناسه تلگرام باید یک عدد صحیح مثبت باشد',
  telegramLinked: 'حساب تلگرام با موفقیت متصل شد',
  telegramLinkError: 'خطا در اتصال تلگرام',
}

const EN: typeof FA = {
  profileSaved: 'Profile saved successfully',
  profileSaveError: 'Error saving profile',
  serverError: 'Server connection error',
  fileTooLarge: 'File must be under 1MB',
  fileLoaded: 'File loaded — click Save to apply',
  fileReadError: 'Error reading file',
  imageTooLarge: 'Image must be under 2MB',
  invalidImageType: 'Unsupported image format. Allowed formats: JPG, PNG, WEBP, GIF',
  avatarUpdated: 'Avatar updated',
  avatarUploadError: 'Upload error',
  removeAvatarConfirm: 'Are you sure you want to remove your profile picture?',
  avatarRemoved: 'Profile picture removed',
  avatarRemoveError: 'Error removing profile picture',
  passwordMismatch: 'Passwords do not match',
  passwordTooShort: 'Password must be at least 8 characters',
  passwordChanged: 'Password changed successfully',
  passwordChangeError: 'Password change error',
  enterTelegramId: 'Enter Telegram ID',
  telegramIdInvalid: 'Telegram ID must be a positive whole number',
  telegramLinked: 'Telegram linked successfully',
  telegramLinkError: 'Telegram link error',
}

export const useProfileDataStrings = dict(FA, EN)
