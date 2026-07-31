/* ═══════════════════════════════════════════════════════════════════════════
   Numerals, money and units — one policy for the whole product.

   Two rules, applied everywhere:

   1. Persian digits, `٬` (U+066C) for thousands and `٫` (U+066B) for the
      decimal mark. Written out by hand rather than delegated to
      `Number.prototype.toLocaleString('fa-IR')`: that call silently returns
      Latin digits on a runtime built with small-icu (which the production
      Node image is), so the same component renders `۱٬۲۵۰٬۰۰۰` in one place
      and `1,250,000` in another. Formatting is cheap; correctness that does
      not depend on the ICU build is worth more.

   2. A number followed by a Latin unit (`ms`, `token`, `tok/s`) must be
      bidi-isolated. Persian digits carry the Unicode bidi class AN, Latin
      letters carry L, and in an RTL paragraph the L run is placed to the
      left of the AN run — so `۱٬۰۰۰٬۰۰۰ token` renders as `token ۱٬۰۰۰٬۰۰۰`.
      Prefer a Persian unit; where the Latin one has to stay, render it
      through <Num unit="…">, which wraps the pair in an LTR isolate.

   A Persian unit needs no isolation: it is an RTL run in an RTL paragraph,
   so `۱٬۲۵۰٬۰۰۰ تومان` already reads number-then-unit right-to-left.
   ═══════════════════════════════════════════════════════════════════════════ */

const FA_DIGITS = '۰۱۲۳۴۵۶۷۸۹'

/** Arabic thousands separator. */
const GROUP = '٬'
/** Arabic decimal separator. */
const DECIMAL = '٫'
/** Real minus, not hyphen-minus — it keeps its shape next to Persian digits. */
const MINUS = '−'

/** Rewrites any Latin digit in a string as its Persian counterpart. */
export function toFaDigits(input: string): string {
  return input.replace(/[0-9]/g, (d) => FA_DIGITS[Number(d)])
}

export type NumOptions = {
  /** Rendered when the value is null/undefined/NaN. */
  fallback?: string
  /** Fixed number of fraction digits. Omit for integers. */
  decimals?: number
  /** Force a leading `+` on positive values (ledger deltas). */
  signed?: boolean
}

/**
 * The one number formatter. Integer by default, because every money value in
 * this product is an integer number of tomans.
 */
export function faNum(
  value: number | null | undefined,
  { fallback = '—', decimals = 0, signed = false }: NumOptions = {},
): string {
  if (value == null || !Number.isFinite(value)) return fallback

  const fixed = Math.abs(value).toFixed(decimals)
  const [whole, fraction] = fixed.split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, GROUP)
  const body = fraction ? `${grouped}${DECIMAL}${fraction}` : grouped

  const sign = value < 0 ? MINUS : signed && value > 0 ? '+' : ''
  return sign + toFaDigits(body)
}

/** Integer tomans plus the unit. The unit is Persian, so no isolation needed. */
export function faPrice(value: number | null | undefined, options?: NumOptions): string {
  const n = faNum(value, options)
  return n === (options?.fallback ?? '—') ? n : `${n} تومان`
}

/**
 * Short form for counts that would otherwise be a wall of digits — token
 * windows, quotas. `۱۲۸ هزار` carries the same information as `۱۲۸٬۰۰۰` and
 * is quicker to compare across a grid of cards.
 */
export function faCompact(value: number | null | undefined, fallback = '—'): string {
  if (value == null || !Number.isFinite(value)) return fallback
  const abs = Math.abs(value)
  if (abs >= 1_000_000) {
    return `${faNum(value / 1_000_000, { decimals: abs % 1_000_000 === 0 ? 0 : 1 })} میلیون`
  }
  if (abs >= 1_000) {
    return `${faNum(value / 1_000, { decimals: abs % 1_000 === 0 ? 0 : 1 })} هزار`
  }
  return faNum(value)
}

/** `٪` is the Persian percent sign; the Latin `%` would need isolating. */
export function faPercent(value: number | null | undefined, decimals = 0, fallback = '—'): string {
  const n = faNum(value, { decimals, fallback })
  return n === fallback ? n : `${n}٪`
}

/** Dates go through Intl (calendar conversion is not something to hand-roll)
    but the digits are normalised afterwards for the same small-icu reason. */
export function faDate(iso: string | null | undefined, fallback = '—'): string {
  if (!iso) return fallback
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return fallback
  return toFaDigits(
    d.toLocaleDateString('fa-IR', { year: 'numeric', month: 'long', day: 'numeric' }),
  )
}

export function faTime(iso: string | null | undefined, fallback = '—'): string {
  if (!iso) return fallback
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return fallback
  return toFaDigits(d.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' }))
}

/** A unit is "Latin" if it contains any Latin letter — those are the ones the
    RTL paragraph reorders. */
const LATIN = /[A-Za-z]/

export type NumProps = {
  value: number | null | undefined
  /** e.g. `تومان`, `توکن`, `ms`, `tok/s`. */
  unit?: string
  /** Use `faCompact` instead of the full grouping. */
  compact?: boolean
  className?: string
  title?: string
} & NumOptions

/**
 * Renders a number, optionally with its unit, under the rules above.
 *
 * `.num` supplies tabular figures so columns of numbers line up; the LTR
 * isolate is applied only when the unit would otherwise jump in front of the
 * digits.
 */
export function Num({
  value,
  unit,
  compact = false,
  className,
  title,
  fallback,
  decimals,
  signed,
}: NumProps) {
  const text = compact
    ? faCompact(value, fallback)
    : faNum(value, { fallback, decimals, signed })

  const classes = className ? `num ${className}` : 'num'

  if (!unit) {
    return (
      <span className={classes} title={title}>
        {text}
      </span>
    )
  }

  // A Latin unit and the digits have to be reordered together, so the pair
  // becomes one LTR isolate: "۷۸۰ ms", never "ms ۷۸۰".
  if (LATIN.test(unit)) {
    return (
      <span className={classes} dir="ltr" title={title}>
        {text} {unit}
      </span>
    )
  }

  return (
    <span className={classes} title={title}>
      {text} <span className="num-unit">{unit}</span>
    </span>
  )
}
