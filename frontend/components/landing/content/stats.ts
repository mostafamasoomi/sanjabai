import { dict } from '@/lib/i18n'
import { MIN_TOPUP_LABEL_FA, MIN_TOPUP_LABEL_EN } from './constants'

/* ── Stats ────────────────────────────────────────────────────────────────── */

const FA = {
  items: [
    { value: '۲۳', label: 'مدل فعال' },
    { value: 'تومان', label: 'واحد پرداخت' },
    { value: '۰', label: 'هزینه‌ی اشتراک ماهانه' },
    { value: MIN_TOPUP_LABEL_FA, label: 'حداقل شارژ کیف پول' },
  ],
}

const EN: typeof FA = {
  items: [
    { value: '23', label: 'active models' },
    { value: 'Toman', label: 'payment currency' },
    { value: '0', label: 'monthly subscription fee' },
    { value: MIN_TOPUP_LABEL_EN, label: 'minimum wallet top-up' },
  ],
}

export const statsContent = dict(FA, EN)
