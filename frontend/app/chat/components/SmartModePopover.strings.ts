import { dict } from '@/lib/i18n'

const FA = {
  title: 'حالت هوشمند',
  triggerOff: 'حالت هوشمند: خاموش',
  trigger: (label: string) => `حالت هوشمند: ${label}`,
  open: 'تنظیم حالت هوشمند',
  close: 'بستن',

  offLabel: 'خاموش',
  offDesc: 'همان مدلی که خودتان انتخاب کرده‌اید پاسخ می‌دهد.',

  autoLabel: 'خودکار',
  autoDesc: 'سنجاب بر پایهٔ قاعده‌های خودش مدل را انتخاب می‌کند. هزینهٔ اضافه ندارد.',

  routerLabel: 'مسیریاب هوشمند',
  routerDesc: 'یک مدل کوچک پیام شما را می‌خواند و مدل مناسب را انتخاب می‌کند.',
  // Money is never quietly spent: the extra call is named before the click.
  routerCost: 'هزینه: برای هر پیام یک درخواست اضافه به آن مدل کوچک زده می‌شود که مثل هر درخواست دیگری از کیف پول شما کم می‌شود.',
  routerFallbackNote: 'اگر مسیریاب نتواند تصمیم بگیرد، انتخاب به حالت خودکار برمی‌گردد.',

  combosHeading: 'ترکیب‌های شما',
  combosLoading: 'در حال بارگذاری ترکیب‌ها…',
  combosError: 'ترکیب‌ها بارگذاری نشد. خاموش، خودکار و مسیریاب همچنان کار می‌کنند.',
  combosEmpty: 'هنوز ترکیبی نساخته‌اید.',
  combosManage: 'ساخت و مدیریت ترکیب‌ها',
  comboItems: (n: string) => `${n} مدل، به همان ترتیبی که چیده‌اید`,
  comboUnknown: (id: string) => `ترکیب شمارهٔ ${id}`,
  comboMissing: 'این ترکیب دیگر در فهرست فعال‌های شما نیست.',

  ranAuto: 'خودکار',
  ranRouter: 'مسیریاب هوشمند',
  fellBack: (asked: string, ran: string) => `«${asked}» را خواسته بودید، ولی این پاسخ با «${ran}» انتخاب شد.`,
  fellBackShort: 'بازگشت به حالت دیگر',
}

const EN: typeof FA = {
  title: 'Smart Mode',
  triggerOff: 'Smart Mode: off',
  trigger: (label: string) => `Smart Mode: ${label}`,
  open: 'Configure Smart Mode',
  close: 'Close',

  offLabel: 'Off',
  offDesc: 'The model you picked yourself answers.',

  autoLabel: 'Automatic',
  autoDesc: 'Sanjabai picks the model with its own rules. No extra cost.',

  routerLabel: 'Smart router',
  routerDesc: 'A small model reads your message and picks the right model for it.',
  routerCost: 'Cost: every message makes one extra call to that small model, billed from your wallet like any other request.',
  routerFallbackNote: 'If the router cannot decide, the pick falls back to automatic.',

  combosHeading: 'Your combos',
  combosLoading: 'Loading combos…',
  combosError: 'Combos failed to load. Off, automatic and router still work.',
  combosEmpty: 'You have not created a combo yet.',
  combosManage: 'Create and manage combos',
  comboItems: (n: string) => `${n} models, in the order you arranged them`,
  comboUnknown: (id: string) => `Combo #${id}`,
  comboMissing: 'This combo is no longer among your enabled ones.',

  ranAuto: 'automatic',
  ranRouter: 'smart router',
  fellBack: (asked: string, ran: string) => `You asked for “${asked}”, but this answer was picked by “${ran}”.`,
  fellBackShort: 'Fell back',
}

export const smartModePopoverStrings = dict(FA, EN)
