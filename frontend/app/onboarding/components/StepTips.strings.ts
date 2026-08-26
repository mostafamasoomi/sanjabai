import { dict } from '@/lib/i18n'

const FA = {
  title: 'سه نکته که کار را راه می‌اندازد',
  subtitle: 'چند ثانیه دیگر و آماده می‌شوید.',
  quickMenuTitle: 'منوی سریع',
  // Split around the ⌘K/Ctrl+K <kbd> element rendered in the component --
  // kept as plain strings (not JSX) so this stays a .strings.ts file.
  quickMenuPrefix: 'با زدن ',
  quickMenuSuffix: ' (یا Ctrl+K) به همه بخش‌ها سریع بروید.',
  switchModelTitle: 'تعویض مدل',
  switchModelBody: 'مدل فعال را از نوار بالای صفحه چت با یک کلیک عوض کنید.',
  balanceTitle: 'موجودی حساب',
  balanceBody: 'هزینه هر چت و موجودی خود را از بخش «کیف پول» دنبال کنید.',
  back: 'قبلی',
  redirecting: 'در حال انتقال...',
  startChat: 'شروع چت',
}

const EN: typeof FA = {
  title: 'Three tips to get you going',
  subtitle: "You'll be ready in a few seconds.",
  quickMenuTitle: 'Quick menu',
  quickMenuPrefix: 'Press ',
  quickMenuSuffix: ' (or Ctrl+K) to jump to any section.',
  switchModelTitle: 'Switch models',
  switchModelBody: 'Change the active model from the bar above the chat with one click.',
  balanceTitle: 'Account balance',
  balanceBody: 'Track the cost of each chat and your balance from the "Wallet" section.',
  back: 'Back',
  redirecting: 'Redirecting...',
  startChat: 'Start chatting',
}

export const stepTipsStrings = dict(FA, EN)
