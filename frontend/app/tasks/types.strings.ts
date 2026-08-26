import { dict } from '@/lib/i18n'

/* Strings for types.ts's constants and pure helpers (DELIVERY_CHANNELS,
 * CRON_PRESETS, STATUS_MAP, describeCron). types.ts is not a component, so
 * these are read with an explicit `lang` argument rather than `useLang()` --
 * see lib/i18n.ts / I18N spec: "a non-component helper takes lang as a
 * parameter instead." */

const FA = {
  deliveryChannels: {
    dashboard: 'داشبورد',
    email: 'ایمیل',
    telegram: 'تلگرام',
  },
  cronPresets: [
    { label: 'هر روز ساعت ۹ صبح', value: '0 9 * * *' },
    { label: 'هر روز ساعت ۱۲ شب', value: '0 0 * * *' },
    { label: 'هر ساعت', value: '0 * * * *' },
    { label: 'هر ۶ ساعت', value: '0 */6 * * *' },
    { label: 'هر هفته (دوشنبه)', value: '0 9 * * 1' },
    { label: 'هر ماه اول', value: '0 9 1 * *' },
  ],
  statusMap: {
    success: 'موفق',
    failed: 'ناموفق',
    running: 'در حال اجرا',
  },
  weekdays: {
    '0': 'یکشنبه', '1': 'دوشنبه', '2': 'سه‌شنبه', '3': 'چهارشنبه',
    '4': 'پنجشنبه', '5': 'جمعه', '6': 'شنبه',
  } as Record<string, string>,
  everyDayAt: (time: string) => `هر روز ساعت ${time}`,
  everyHour: 'هر ساعت',
  everyNMinutes: (n: string) => `هر ${n} دقیقه`,
  everyWeekdayAt: (day: string, time: string) => `هر ${day} ساعت ${time}`,
  everyWeekday: (day: string) => `هر ${day}`,
}

const EN: typeof FA = {
  deliveryChannels: {
    dashboard: 'Dashboard',
    email: 'Email',
    telegram: 'Telegram',
  },
  cronPresets: [
    { label: 'Every day at 9 AM', value: '0 9 * * *' },
    { label: 'Every day at midnight', value: '0 0 * * *' },
    { label: 'Every hour', value: '0 * * * *' },
    { label: 'Every 6 hours', value: '0 */6 * * *' },
    { label: 'Every week (Monday)', value: '0 9 * * 1' },
    { label: 'First of every month', value: '0 9 1 * *' },
  ],
  statusMap: {
    success: 'Success',
    failed: 'Failed',
    running: 'Running',
  },
  weekdays: {
    '0': 'Sunday', '1': 'Monday', '2': 'Tuesday', '3': 'Wednesday',
    '4': 'Thursday', '5': 'Friday', '6': 'Saturday',
  },
  everyDayAt: (time) => `Every day at ${time}`,
  everyHour: 'Every hour',
  everyNMinutes: (n) => `Every ${n} minutes`,
  everyWeekdayAt: (day, time) => `Every ${day} at ${time}`,
  everyWeekday: (day) => `Every ${day}`,
}

export const tasksTypesStrings = dict(FA, EN)
