import { dict } from '@/lib/i18n'

const FA = {
  title: 'درصد به ازای هر مدل',
  searchPlaceholder: 'جستجوی مدل…',
  // Interpolated rather than concatenated: word order differs between the
  // two languages.
  summary: (count: string, page: string, pageCount: string) => `${count} مدل یافت شد — صفحهٔ ${page} از ${pageCount}`,
  deselectAllFiltered: 'لغو انتخاب همهٔ نتایج (همهٔ صفحات)',
  selectAllFiltered: (count: string) => `انتخاب همهٔ ${count} نتیجه (همهٔ صفحات)`,

  selectPageAria: 'انتخاب همهٔ این صفحه',
  selectPageTitle: 'فقط ردیف‌های همین صفحه را انتخاب می‌کند',
  selectRowAria: (name: string) => `انتخاب ${name}`,

  colModel: 'مدل',
  colBaseInput: 'قیمت پایه ورودی',
  colBaseOutput: 'قیمت پایه خروجی',
  colEffectivePct: 'درصد مؤثر',
  colInputAfterMarkup: 'قیمت ورودی پس از سود',
  colOverride: 'override این مدل',
  colActions: 'عملیات',

  loading: 'در حال بارگذاری…',
  retry: 'تلاش دوباره',
  noModels: 'مدلی یافت نشد',

  inheritedTitle: 'ارث‌برده از درصد سراسری',
  overrideTitle: 'override اختصاصی این مدل',
  globalSuffix: ' (سراسری)',

  overridePlaceholder: 'سراسری',
  saveEmptyTitle: 'خالی = پاک کردن override',
  saveTitle: 'ذخیره override',

  page: (page: string, pageCount: string) => `صفحهٔ ${page} از ${pageCount}`,
  prev: 'قبلی',
  next: 'بعدی',
}

const EN: typeof FA = {
  title: 'Markup per model',
  searchPlaceholder: 'Search models…',
  summary: (count, page, pageCount) => `${count} models found — page ${page} of ${pageCount}`,
  deselectAllFiltered: 'Deselect all results (all pages)',
  selectAllFiltered: (count) => `Select all ${count} results (all pages)`,

  selectPageAria: 'Select all on this page',
  selectPageTitle: 'Only selects the rows on this page',
  selectRowAria: (name) => `Select ${name}`,

  colModel: 'Model',
  colBaseInput: 'Base input price',
  colBaseOutput: 'Base output price',
  colEffectivePct: 'Effective markup',
  colInputAfterMarkup: 'Input price after markup',
  colOverride: "This model's override",
  colActions: 'Actions',

  loading: 'Loading…',
  retry: 'Retry',
  noModels: 'No models found',

  inheritedTitle: 'Inherited from the global percentage',
  overrideTitle: "This model's dedicated override",
  globalSuffix: ' (global)',

  overridePlaceholder: 'Global',
  saveEmptyTitle: 'Empty = clear override',
  saveTitle: 'Save override',

  page: (page, pageCount) => `Page ${page} of ${pageCount}`,
  prev: 'Previous',
  next: 'Next',
}

export const markupModelsTableStrings = dict(FA, EN)
