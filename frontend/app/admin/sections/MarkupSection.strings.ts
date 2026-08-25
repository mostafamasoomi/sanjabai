import { dict } from '@/lib/adminI18n'

const FA = {
  title: 'درصد سود',
  subtitle:
    'یک درصد سراسری روی همهٔ مدل‌ها، به‌علاوهٔ امکان override روی هر مدل — مدل بدون override از درصد سراسری ارث می‌برد',

  globalTitle: 'درصد سراسری',
  globalSubtitle: 'روی همهٔ مدل‌هایی که override اختصاصی ندارند اعمال می‌شود.',
  globalFieldLabel: 'درصد سود سراسری',
  saveGlobal: 'ذخیره درصد سراسری',
  globalPreview: (base: string, result: string) => `نمونه: قیمت پایه ${base} با این درصد می‌شود ${result}`,

  bulkTitle: 'ویرایش گروهی',
  bulkNoneSelected: 'از جدول زیر مدل‌ها را انتخاب کنید',
  bulkSelected: (n: string) => `${n} مدل انتخاب شده`,
  bulkFieldLabel: 'درصد سود برای مدل‌های انتخاب‌شده',
  applyToSelected: 'اعمال روی انتخاب‌شده‌ها',
  clearOverride: 'پاک کردن override',
  clearOverrideTitle: 'override این مدل‌ها را پاک می‌کند تا دوباره از درصد سراسری ارث ببرند',

  // Toasts
  loadErrorToast: 'خطا در دریافت اطلاعات درصد سود',
  globalSavedToast: 'درصد سراسری ذخیره شد',
  globalSaveFailedToast: 'ذخیره درصد سراسری ناموفق بود',
  overrideClearedToast: 'override پاک شد — این مدل درصد سراسری را دارد',
  overrideSavedToast: 'override این مدل ذخیره شد',
  rowSaveFailedToast: 'ذخیره ناموفق بود',
  selectAtLeastOneToast: 'حداقل یک مدل را انتخاب کنید',
  bulkUpdatedToast: (n: string) => `${n} مدل به‌روزرسانی شد`,
  bulkFailedToast: 'اعمال گروهی ناموفق بود',

  // Validation (mirrors backend/admin_catalog.py's _parse_markup_pct)
  negativePctError: 'درصد سود نمی‌تواند منفی باشد (هیچ درخواستی نباید ضررده باشد)',
  aboveMaxPctError: (max: string) => `درصد سود نمی‌تواند بیش از ${max}٪ باشد`,

  percentSign: '٪',
}

const EN: typeof FA = {
  title: 'Markup',
  subtitle:
    'A global percentage applied to every model, plus a per-model override — a model with no override inherits the global percentage',

  globalTitle: 'Global percentage',
  globalSubtitle: 'Applied to every model that has no dedicated override.',
  globalFieldLabel: 'Global markup percentage',
  saveGlobal: 'Save global percentage',
  globalPreview: (base, result) => `Example: base price ${base} becomes ${result} at this percentage`,

  bulkTitle: 'Bulk edit',
  bulkNoneSelected: 'Select models from the table below',
  bulkSelected: (n) => `${n} model${n === '1' ? '' : 's'} selected`,
  bulkFieldLabel: 'Markup for selected models',
  applyToSelected: 'Apply to selected',
  clearOverride: 'Clear override',
  clearOverrideTitle: 'Clears the override for these models so they inherit the global percentage again',

  loadErrorToast: 'Failed to load markup data',
  globalSavedToast: 'Global percentage saved',
  globalSaveFailedToast: 'Failed to save the global percentage',
  overrideClearedToast: 'Override cleared — this model now uses the global percentage',
  overrideSavedToast: "This model's override was saved",
  rowSaveFailedToast: 'Save failed',
  selectAtLeastOneToast: 'Select at least one model',
  bulkUpdatedToast: (n) => `${n} model${n === '1' ? '' : 's'} updated`,
  bulkFailedToast: 'Bulk apply failed',

  negativePctError: 'Markup cannot be negative (no request may sell at a loss)',
  aboveMaxPctError: (max) => `Markup cannot exceed ${max}%`,

  percentSign: '%',
}

export const markupSectionStrings = dict(FA, EN)
