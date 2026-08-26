import { toFaDigits } from '@/lib/format'
import { dict } from '@/lib/i18n'
import type { Lang } from '@/components/LanguageToggle'

// ─── Constants ──────────────────────────────────────────────────────────────
// Bare values only -- no baked-in label. TopupCard renders each preset's
// label with `f.compact(value)` (lib/i18n's language-bound formatter), which
// reproduces the old hard-coded Persian labels exactly for 'fa' and gives a
// real English compact form ("100K", "1M") for 'en'.
export const PRESET_AMOUNTS = [100_000, 500_000, 1_000_000, 5_000_000]

export const MIN_TOPUP = 10_000
export const MAX_TOPUP = 100_000_000_000

// ─── Helpers ────────────────────────────────────────────────────────────────
// Money and plain numbers go through fmt(lang) from lib/i18n (f.price /
// f.num) at the call site -- no page-local money formatter lives here any
// more; one used to wrap `faNum` under a name that implied a different
// currency, and that mismatch is exactly what caused this page's toman/rial
// mixups.
//
// The ledger/payment tables need a date+time format one step more compact
// than lib/i18n's `f.date` (short month, no weekday, minutes included in the
// same call), so that one stays here as a small helper parameterised by
// `lang` rather than a hook -- see lib/i18n.ts's completeness-check comment
// for why `useLang()` itself is reserved for component bodies.
export function fmtDate(s: string, lang: Lang): string {
  const d = new Date(s)
  const opts: Intl.DateTimeFormatOptions = {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }
  return lang === 'fa'
    ? toFaDigits(d.toLocaleDateString('fa-IR', opts))
    : d.toLocaleDateString('en-GB', opts)
}

const STATUS_LABEL_FA: Record<string, { text: string; badge: string }> = {
  paid: { text: 'موفق', badge: 'badge-positive' },
  success: { text: 'موفق', badge: 'badge-positive' },
  pending: { text: 'در انتظار', badge: 'badge-warning' },
  failed: { text: 'ناموفق', badge: 'badge-danger' },
  cancelled: { text: 'لغو شده', badge: 'badge-danger' },
}

const STATUS_LABEL_EN: typeof STATUS_LABEL_FA = {
  paid: { text: 'Paid', badge: 'badge-positive' },
  success: { text: 'Paid', badge: 'badge-positive' },
  pending: { text: 'Pending', badge: 'badge-warning' },
  failed: { text: 'Failed', badge: 'badge-danger' },
  cancelled: { text: 'Cancelled', badge: 'badge-danger' },
}

/** `statusLabel(lang)[p.status]` -- a payment/ledger status code (backend
 *  enum value, not user-facing Persian) mapped to its badge text+class. */
export const statusLabel = dict(STATUS_LABEL_FA, STATUS_LABEL_EN)
