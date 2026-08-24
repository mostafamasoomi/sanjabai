import { faPrice, toFaDigits } from '@/lib/format'

// ─── Constants ──────────────────────────────────────────────────────────────
export const PRESET_AMOUNTS = [
  { label: '۱۰۰ هزار', value: 100_000 },
  { label: '۵۰۰ هزار', value: 500_000 },
  { label: '۱ میلیون', value: 1_000_000 },
  { label: '۵ میلیون', value: 5_000_000 },
]

export const MIN_TOPUP = 10_000
export const MAX_TOPUP = 100_000_000_000

// ─── Helpers ────────────────────────────────────────────────────────────────
// Numerals and money go through lib/format so every surface agrees; see the
// note there on why toLocaleString is not called directly. No page-local
// money-formatter alias lives here any more -- one used to wrap `faNum`
// under a name that implied a different currency, and that mismatch is
// exactly what caused this page's toman/rial mixups. Call `faNum` /
// `faPrice` from lib/format directly.
export const fmtToman = (n: number) => faPrice(n)
export const fmtDate = (s: string) =>
  toFaDigits(
    new Date(s).toLocaleDateString('fa-IR', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }),
  )

export const statusLabel: Record<string, { text: string; badge: string }> = {
  paid: { text: 'موفق', badge: 'badge-positive' },
  success: { text: 'موفق', badge: 'badge-positive' },
  pending: { text: 'در انتظار', badge: 'badge-warning' },
  failed: { text: 'ناموفق', badge: 'badge-danger' },
  cancelled: { text: 'لغو شده', badge: 'badge-danger' },
}
