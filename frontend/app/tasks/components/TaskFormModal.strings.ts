import { dict } from '@/lib/i18n'

const FA = {
  editTitle: 'ویرایش تسک',
  createTitle: 'ایجاد تسک جدید',
  title: 'عنوان',
  titlePlaceholder: 'مثلاً: خلاصه روزانه اخبار',
  description: 'توضیحات',
  descriptionPlaceholder: 'توضیح کوتاه درباره این تسک...',
  prompt: 'پرامپت',
  promptPlaceholder: 'پرامپتی که قرار است اجرا شود...',
  model: 'مدل',
  autoSelect: 'انتخاب خودکار (پیشنهاد سیستم)',
  loadingModels: 'در حال دریافت فهرست مدل‌ها...',
  noModelsAvailable: 'مدلی در دسترس نیست — به‌صورت خودکار انتخاب می‌شود',
  cronLabel: 'زمان‌بندی (Cron Expression)',
  cronFormatHint: (example: string) => `فرمت: دقیقه ساعت روز ماه ماه روز_هفته — مثال: ${example} = هر روز ساعت ۹ صبح`,
  deliveryChannel: 'کانال ارسال نتیجه',
  save: 'ذخیره',
}

const EN: typeof FA = {
  editTitle: 'Edit task',
  createTitle: 'Create new task',
  title: 'Title',
  titlePlaceholder: 'e.g. Daily news summary',
  description: 'Description',
  descriptionPlaceholder: 'A short description of this task...',
  prompt: 'Prompt',
  promptPlaceholder: 'The prompt that will be run...',
  model: 'Model',
  autoSelect: 'Auto-select (system suggestion)',
  loadingModels: 'Loading model list...',
  noModelsAvailable: 'No model available — one will be chosen automatically',
  cronLabel: 'Schedule (Cron expression)',
  cronFormatHint: (example: string) => `Format: minute hour day month weekday — example: ${example} = every day at 9 AM`,
  deliveryChannel: 'Result delivery channel',
  save: 'Save',
}

export const taskFormModalStrings = dict(FA, EN)
