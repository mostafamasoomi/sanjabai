/* ── Footer ───────────────────────────────────────────────────────────────── */

export const FOOTER_COLUMNS = [
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
] as const
