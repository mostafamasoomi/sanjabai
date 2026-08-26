import { dict } from '@/lib/i18n'

/* Sibling to page.tsx. See lib/i18n.ts for why `EN: typeof FA` (and the
   absence of `as const` on FA) is what makes a missing key a build error. */

const FA = {
  title: 'تولید تصویر',
  subtitle: 'توضیح متنی خود را بنویسید و از یک مدل تولید تصویر فعال، تصویر بسازید',
  catalogErrorToast: 'خطا در دریافت فهرست مدل‌ها',
  catalogErrorTitle: 'خطا در دریافت فهرست مدل‌ها',
  catalogErrorDesc: 'اتصال به سرور برقرار نشد. لطفاً صفحه را دوباره بارگذاری کنید.',
  noModelsTitle: 'در حال حاضر هیچ مدل تولید تصویری فعال نیست',
  noModelsDesc: 'مدل‌های تولید تصویر پس از تأیید با پروب زنده و ثبت قیمت، اینجا نمایش داده می‌شوند.',
  modelLabel: 'مدل',
  promptLabel: 'توضیح تصویر',
  promptPlaceholder: 'مثلاً: یک منظره کوهستانی در غروب آفتاب',
  countLabel: (max: string) => `تعداد تصویر (حداکثر ${max})`,
  sizeLabel: 'اندازه تصویر',
  sizeDefault: 'پیش‌فرض',
  submit: 'تولید تصویر',
  noImagesReceived: 'تولید تصویر ناموفق بود؛ هیچ تصویری از سرویس دریافت نشد',
  networkError: 'خطا در ارتباط با سرور. اتصال اینترنت خود را بررسی کنید و دوباره تلاش کنید.',
}

const EN: typeof FA = {
  title: 'Image generation',
  subtitle: 'Write a text description and generate images with an active image model',
  catalogErrorToast: 'Failed to load the model list',
  catalogErrorTitle: 'Failed to load the model list',
  catalogErrorDesc: 'Could not connect to the server. Please reload the page.',
  noModelsTitle: 'No image generation model is active right now',
  noModelsDesc: 'Image models appear here once confirmed by a live probe and given a price.',
  modelLabel: 'Model',
  promptLabel: 'Image description',
  promptPlaceholder: 'e.g. a mountain landscape at sunset',
  countLabel: (max) => `Number of images (max ${max})`,
  sizeLabel: 'Image size',
  sizeDefault: 'Default',
  submit: 'Generate image',
  noImagesReceived: 'Image generation failed; no image was received from the service',
  networkError: 'Connection to the server failed. Check your internet connection and try again.',
}

export const imagesPageStrings = dict(FA, EN)
