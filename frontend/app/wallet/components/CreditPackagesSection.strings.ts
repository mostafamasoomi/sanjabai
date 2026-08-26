import { dict } from '@/lib/i18n'

const FA = {
  // The unit rendered as its own muted span beside the figure, so it
  // cannot come from f.price() -- but it still belongs here, not in a
  // ternary in the markup.
  tomanUnit: 'تومان',
  title: 'بسته‌های اعتباری',
  noneTitle: 'بسته‌ای موجود نیست',
  noneDesc: 'در حال حاضر بسته اعتباری برای خرید وجود ندارد.',
  bonus: (pct: number) => `${pct}%+ بونوس`,
  youPay: (n: string) => `شما ${n} تومان پرداخت می‌کنید`,
  bonusAmount: (n: string) => `+ ${n} تومان بونوس`,
  equivalent: (price: string) => `معادل ${price}`,
  approxTokens: (n: string, model: string) => `≈ ${n} میلیون توکن ${model} (بر اساس نرخ خروجی فعلی)`,
  processing: 'در حال پردازش...',
  buyPackage: 'خرید بسته',
}

const EN: typeof FA = {
  tomanUnit: 'Toman',
  title: 'Credit Packages',
  noneTitle: 'No packages available',
  noneDesc: 'There are no credit packages to buy right now.',
  bonus: (pct) => `+${pct}% bonus`,
  youPay: (n) => `You pay ${n} Toman`,
  bonusAmount: (n) => `+ ${n} Toman bonus`,
  equivalent: (price) => `Equivalent to ${price}`,
  approxTokens: (n, model) => `≈ ${n}M tokens on ${model} (based on the current output rate)`,
  processing: 'Processing...',
  buyPackage: 'Buy package',
}

export const creditPackagesSectionStrings = dict(FA, EN)
