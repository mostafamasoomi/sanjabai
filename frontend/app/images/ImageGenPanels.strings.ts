import { dict } from '@/lib/i18n'

/* Sibling to ImageGenPanels.tsx. See lib/i18n.ts for why `EN: typeof FA`
   (and the absence of `as const` on FA) is what makes a missing key a
   build error. */

const FA = {
  pickerAriaLabel: 'انتخاب مدل تولید تصویر',
  loginPrompt: 'لطفاً وارد حساب خود شوید',
  loginAction: 'ورود',
  insufficientBalance: 'موجودی کیف پول شما کافی نیست. لطفاً حساب خود را شارژ کنید.',
  topUpAction: 'شارژ کیف پول',
  modelNotAvailable: 'این مدل برای تولید تصویر در دسترس نیست',
  priceNotSet: 'قیمتی برای این مدل ثبت نشده است؛ این مدل قابل ارائه نیست',
  noImages: 'تولید تصویر ناموفق بود؛ هیچ تصویری از سرویس دریافت نشد',
  modelRequired: 'مدل مشخص نشده است',
  serviceUnavailable: (status: string) => `سرویس موقتاً در دسترس نیست (کد ${status})`,
  generating: 'در حال تولید تصویر... تولید تصویر ممکن است تا چند دقیقه طول بکشد. این صفحه را نبندید.',
  generatedImageAlt: (n: string) => `تصویر تولیدشده ${n}`,
  requestCost: (price: string) => `هزینه این درخواست: ${price}`,
}

const EN: typeof FA = {
  pickerAriaLabel: 'Choose an image generation model',
  loginPrompt: 'Please sign in to your account',
  loginAction: 'Sign in',
  insufficientBalance: 'Your wallet balance is insufficient. Please top up your account.',
  topUpAction: 'Top up wallet',
  modelNotAvailable: 'This model is not available for image generation',
  priceNotSet: 'No price is set for this model; it cannot be offered',
  noImages: 'Image generation failed; no image was received from the service',
  modelRequired: 'No model specified',
  serviceUnavailable: (status) => `The service is temporarily unavailable (code ${status})`,
  generating: 'Generating image... this can take a few minutes. Please don’t close this page.',
  generatedImageAlt: (n) => `Generated image ${n}`,
  requestCost: (price) => `Cost of this request: ${price}`,
}

export const imageGenPanelsStrings = dict(FA, EN)
