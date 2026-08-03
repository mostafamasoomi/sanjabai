import { CheckGlyph } from './primitives'
import { COMPARISON_ROWS } from './content'

/**
 * Restates claims already established elsewhere on the page (STATS,
 * PRICING_COLUMNS, HERO_TRUST, FAQ) side-by-side with the general pattern
 * subscription services share — see the header comment on COMPARISON_ROWS
 * in content.ts for why the right column stays unnamed and unquantified.
 */
export function ComparisonSection() {
  return (
    <section className="lp-section lp-section--soft" id="comparison">
      <div className="lp-container">
        <header className="lp-head">
          <h2 className="lp-title">چرا پرداخت به‌ازای مصرف، نه اشتراک ماهانه؟</h2>
          <p className="lp-lead">تفاوت سنجاب‌ای با سرویس‌های اشتراکی رایج، در یک نگاه.</p>
        </header>

        {/* The table is wider than a phone screen (3 columns of real content
            don't fit in ~350px) — .lp-compare scrolls horizontally, but a
            scroll affordance nobody notices is the same as no affordance, so
            this is a plain-text hint rather than a subtle edge gradient. Only
            shown under the breakpoint where scrolling is actually needed. */}
        <p className="lp-compare__hint">برای مقایسه‌ی کامل، جدول را به چپ بکشید ⟵</p>

        <div className="lp-compare">
          <table className="lp-compare__table">
            <thead>
              <tr>
                <th scope="col" />
                <th scope="col" className="lp-compare__col--brand">
                  <span dir="ltr">Sanjabai</span>
                </th>
                <th scope="col">سرویس‌های اشتراکی رایج</th>
              </tr>
            </thead>
            <tbody>
              {COMPARISON_ROWS.map((row) => (
                <tr key={row.label}>
                  <th scope="row">{row.label}</th>
                  <td className="lp-compare__col--brand">
                    <span className="lp-compare__value">
                      <CheckGlyph size={14} />
                      {row.sanjabai}
                    </span>
                  </td>
                  <td>{row.subscription}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
