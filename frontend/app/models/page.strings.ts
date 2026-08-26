import { dict } from '@/lib/i18n'
import type { Availability } from '@/types/catalog'
import type { ContextBand } from '@/lib/useCatalog'

/* Sibling to page.tsx. See lib/i18n.ts for why `EN: typeof FA` (and the
   absence of `as const` on FA) is what makes a missing key a build error.

   Model health labels come from `healthLabel(lang)` and price-band labels
   from `priceBandLabel(band, lang)` — both bilingual readers on shared files
   this agent does not own (app/chat/components/modelUtils.ts,
   lib/useCatalog.ts). `contextBand` below is a local English mirror of
   `CONTEXT_BAND_LABEL` in lib/useCatalog.ts, which — unlike its price-band
   neighbour — is still a plain `Record<ContextBand, string>`, not a
   `(band, lang) => label` reader. If it gains one, prefer that and drop the
   local copy here. */

const FA = {
  pageTitle: 'مدل‌های هوش مصنوعی',
  pageSubtitle: 'همه مدل‌ها از یک پنل — وضعیت هر مدل به‌صورت زنده اندازه‌گیری می‌شود.',
  searchPlaceholder: 'جستجو در نام یا توضیح مدل...',
  searchAriaLabel: 'جستجوی مدل',
  clearSearchAriaLabel: 'پاک کردن جستجو',
  priceFilterLabel: 'قیمت:',
  contextFilterLabel: 'پنجره‌ی متن:',
  all: 'همه',
  clearFilters: 'پاک کردن فیلترها',
  resultCount: (shown: string) => `${shown} مدل`,
  resultCountOfTotal: (shown: string, total: string) => `${shown} مدل از ${total}`,
  loadErrorToast: 'خطا در دریافت فهرست مدل‌ها',
  loadErrorTitle: 'خطا در بارگذاری',
  loadErrorDesc: 'در حال حاضر امکان دریافت فهرست مدل‌ها وجود ندارد. لطفاً بعداً تلاش کنید.',
  emptyTitle: 'مدلی یافت نشد',
  emptyDescFiltered: 'برای فیلترها و عبارت جستجوی انتخابی شما مدلی موجود نیست.',
  emptyDescUnfiltered: 'در حال حاضر مدلی در فهرست موجود نیست.',
  noDescription: 'بدون توضیح',
  contextWindow: 'پنجره‌ی متن',
  latency: 'تأخیر میانه',
  inputPerMillion: 'ورودی / میلیون',
  tokenUnit: 'توکن',
  startChat: 'شروع چت',
  startChatAria: (name: string) => `شروع چت با ${name}`,
  unavailable: 'در دسترس نیست',
  unavailableTitle: 'این مدل در حال حاضر در دسترس نیست',
  unavailableAria: (name: string) => `${name} در حال حاضر در دسترس نیست`,
  availabilityNote: {
    maintenance: 'در حال نگهداری',
    disabled: 'غیرفعال',
  } as Partial<Record<Availability, string>>,
  contextBand: {
    small: 'کوچک (تا ۳۲ هزار توکن)',
    medium: 'متوسط (تا ۱۵۰ هزار توکن)',
    large: 'بزرگ (تا ۶۰۰ هزار توکن)',
    xlarge: 'خیلی‌بزرگ (بیش از ۶۰۰ هزار توکن)',
  } as Record<ContextBand, string>,
}

const EN: typeof FA = {
  pageTitle: 'AI models',
  pageSubtitle: 'Every model from one panel — each model’s status is measured live.',
  searchPlaceholder: 'Search model name or description...',
  searchAriaLabel: 'Search models',
  clearSearchAriaLabel: 'Clear search',
  priceFilterLabel: 'Price:',
  contextFilterLabel: 'Context window:',
  all: 'All',
  clearFilters: 'Clear filters',
  resultCount: (shown) => `${shown} model${shown === '1' ? '' : 's'}`,
  resultCountOfTotal: (shown, total) => `${shown} of ${total} models`,
  loadErrorToast: 'Failed to load the model list',
  loadErrorTitle: 'Failed to load',
  loadErrorDesc: 'The model list can’t be fetched right now. Please try again later.',
  emptyTitle: 'No models found',
  emptyDescFiltered: 'No model matches your selected filters and search term.',
  emptyDescUnfiltered: 'There are no models in the list right now.',
  noDescription: 'No description',
  contextWindow: 'Context window',
  latency: 'Median latency',
  inputPerMillion: 'Input / million',
  tokenUnit: 'tokens',
  startChat: 'Start chat',
  startChatAria: (name) => `Start a chat with ${name}`,
  unavailable: 'Unavailable',
  unavailableTitle: 'This model is currently unavailable',
  unavailableAria: (name) => `${name} is currently unavailable`,
  availabilityNote: {
    maintenance: 'Under maintenance',
    disabled: 'Disabled',
  },
  contextBand: {
    small: 'Small (up to 32K tokens)',
    medium: 'Medium (up to 150K tokens)',
    large: 'Large (up to 600K tokens)',
    xlarge: 'Extra large (over 600K tokens)',
  },
}

export const modelsPageStrings = dict(FA, EN)
