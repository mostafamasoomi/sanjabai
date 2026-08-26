import { dict } from '@/lib/i18n'

/* ── Footer ───────────────────────────────────────────────────────────────── */

const FA = {
  columns: [
    {
      title: 'محصول',
      links: [
        { label: 'چت', href: '/chat' },
        { label: 'مدل‌ها', href: '/models' },
        { label: 'مقایسه‌ی مدل‌ها', href: '/compare' },
        { label: 'عامل‌ها و مهارت‌ها', href: '/skills' },
        { label: 'تعرفه‌ها', href: '/pricing' },
      ],
    },
    {
      title: 'توسعه‌دهندگان',
      links: [
        { label: 'مستندات API', href: '/developer' },
        { label: 'کلیدهای API', href: '/api-keys' },
        { label: 'زمین بازی', href: '/playground' },
        { label: 'گزارش مصرف', href: '/usage' },
      ],
    },
    {
      title: 'حساب کاربری',
      links: [
        { label: 'ورود', href: '/login' },
        { label: 'ثبت‌نام', href: '/signup' },
        { label: 'کیف پول', href: '/wallet' },
        { label: 'دعوت دوستان', href: '/referral' },
      ],
    },
  ],
}

const EN: typeof FA = {
  columns: [
    {
      title: 'Product',
      links: [
        { label: 'Chat', href: '/chat' },
        { label: 'Models', href: '/models' },
        { label: 'Compare models', href: '/compare' },
        { label: 'Agents & skills', href: '/skills' },
        { label: 'Pricing', href: '/pricing' },
      ],
    },
    {
      title: 'Developers',
      links: [
        { label: 'API docs', href: '/developer' },
        { label: 'API keys', href: '/api-keys' },
        { label: 'Playground', href: '/playground' },
        { label: 'Usage report', href: '/usage' },
      ],
    },
    {
      title: 'Account',
      links: [
        { label: 'Sign in', href: '/login' },
        { label: 'Sign up', href: '/signup' },
        { label: 'Wallet', href: '/wallet' },
        { label: 'Refer a friend', href: '/referral' },
      ],
    },
  ],
}

export const footerContent = dict(FA, EN)
