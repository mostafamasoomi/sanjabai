import { dict } from '@/lib/i18n'

const FA = {
  titlePrefix: 'مدل پیشنهادی برای «',
  titleSuffix: '»',
  subtitleWithFavorites: 'بر اساس مدل‌های موردعلاقه و هدف شما، این مدل پیشنهاد می‌شود.',
  subtitleDefault: 'این مدل برای نیاز شما بهینه شده — هر وقت خواستید می‌توانید عوضش کنید.',
  fromCatalog: 'از کاتالوگ زنده',
  defaultSuggestion: 'پیشنهاد پیشفرض',
  fromFavorites: 'از علاقه‌مندی‌ها',
  contextSuffix: 'کانتکست',
  back: 'قبلی',
  moreTips: 'نکات بعدی',
  redirecting: 'در حال انتقال...',
  startChat: 'شروع چت',
}

const EN: typeof FA = {
  titlePrefix: 'Recommended model for “',
  titleSuffix: '”',
  subtitleWithFavorites: 'Based on your favorite models and your goal, this model is recommended.',
  subtitleDefault: "This model is tuned for your needs — you can change it any time.",
  fromCatalog: 'From live catalog',
  defaultSuggestion: 'Default suggestion',
  fromFavorites: 'From favorites',
  contextSuffix: 'context',
  back: 'Back',
  moreTips: 'More tips',
  redirecting: 'Redirecting...',
  startChat: 'Start chatting',
}

export const stepRecommendStrings = dict(FA, EN)
