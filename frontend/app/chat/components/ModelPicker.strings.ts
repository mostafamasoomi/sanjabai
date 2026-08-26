import { dict } from '@/lib/i18n'

const FA = {
  noModelSelected: 'انتخاب مدل',
  statusLabel: (status: string) => `وضعیت: ${status}`,
  selectModel: 'انتخاب مدل',
  smartModeNote: 'Smart Mode فعال — انتخاب خودکار مدل',
  searchPlaceholder: 'جستجوی مدل، قابلیت...',
  noModelFound: (query: string) => `مدلی با "${query}" یافت نشد`,
  recommended: 'پیشنهادی',
  allModels: 'همه مدل‌ها',
  modelsCount: (n: string) => `${n} مدل`,
  navigate: 'پیمایش',
  select: 'انتخاب',
  close: 'بستن',
  inputPricing: 'ورودی هر میلیون توکن',
  input: 'ورودی',
  outputPricing: 'خروجی هر میلیون توکن',
  output: 'خروجی',
}

const EN: typeof FA = {
  noModelSelected: 'Select a model',
  statusLabel: (status: string) => `Status: ${status}`,
  selectModel: 'Select a model',
  smartModeNote: 'Smart Mode is on — model is picked automatically',
  searchPlaceholder: 'Search model, capability...',
  noModelFound: (query: string) => `No model found for "${query}"`,
  recommended: 'Recommended',
  allModels: 'All models',
  modelsCount: (n: string) => `${n} models`,
  navigate: 'navigate',
  select: 'select',
  close: 'close',
  inputPricing: 'Input per million tokens',
  input: 'Input',
  outputPricing: 'Output per million tokens',
  output: 'Output',
}

export const modelPickerStrings = dict(FA, EN)
