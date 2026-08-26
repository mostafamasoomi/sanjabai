import { dict } from '@/lib/i18n'

/* ── Navigation ───────────────────────────────────────────────────────────── */

const FA = {
  links: [
    { label: 'امکانات', href: '#features' },
    { label: 'مدل‌ها', href: '/models' },
    { label: 'تعرفه‌ها', href: '/pricing' },
    { label: 'مستندات', href: '/developer' },
  ],
}

const EN: typeof FA = {
  links: [
    { label: 'Features', href: '#features' },
    { label: 'Models', href: '/models' },
    { label: 'Pricing', href: '/pricing' },
    { label: 'Docs', href: '/developer' },
  ],
}

export const navContent = dict(FA, EN)
