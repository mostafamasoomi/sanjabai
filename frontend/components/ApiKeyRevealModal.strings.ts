import { dict } from '@/lib/i18n'

const FA = {
  rotated: 'کلید چرخانده شد',
  created: 'کلید جدید ساخته شد',
  warning: 'این کلید فقط همین یک بار نمایش داده می‌شود و در هیچ جای دیگری (حتی برای خودتان) دوباره قابل مشاهده نیست. همین حالا آن را در جای امنی ذخیره کنید.',
  rotationWarningSuffix: ' کلید قبلی از این لحظه دیگر کار نمی‌کند.',
  apiKeyLabel: 'کلید API',
  copy: 'کپی',
  copied: 'کپی شد',
  copyFailed: 'کپی خودکار انجام نشد. متن کلید انتخاب شد — با Ctrl+C (یا Cmd+C) آن را کپی کنید.',
  copyHint: 'در صورت خطای کپی خودکار، روی کادر کلید کلیک کنید تا متن انتخاب شود.',
  acknowledge: 'کلید را ذخیره کردم',
}

const EN: typeof FA = {
  rotated: 'Key rotated',
  created: 'New key created',
  warning: 'This key is shown only this one time and cannot be viewed again anywhere -- not even by you. Save it somewhere safe right now.',
  rotationWarningSuffix: ' The previous key stops working from this moment on.',
  apiKeyLabel: 'API key',
  copy: 'Copy',
  copied: 'Copied',
  copyFailed: 'Automatic copy failed. The key text was selected -- copy it with Ctrl+C (or Cmd+C).',
  copyHint: 'If automatic copy fails, click the key field to select the text.',
  acknowledge: "I've saved the key",
}

export const apiKeyRevealModalStrings = dict(FA, EN)
