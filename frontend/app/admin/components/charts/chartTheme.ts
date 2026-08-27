/* ═══════════════════════════════════════════════════════════════════════════
   Per-metric colors for the admin chart kit.

   Every color is a CSS custom property that exists in app/globals.css, never
   a hex literal — the palette follows the light/dark toggle for free. The
   semantic tokens (--positive/--danger/--warning/--info) and the accent
   family are all overridden in the `[data-theme='light']` block with values
   darkened to clear WCAG 4.5:1 on cream; --accent-purple is deliberately
   NOT overridden there because its dark-theme value already clears 4.5:1 on
   the light surface (globals.css documents both facts inline). So each
   var() below is legible in both themes by construction.

   The assignment is semantic, not decorative: money-in is green, money-out
   is red, and the four money metrics (revenue/cost/margin/net) are mutually
   distinct because they share one axis on the profit chart; likewise the
   growth pair (users/conversations).
   ═══════════════════════════════════════════════════════════════════════════ */

export type ChartMetric =
  | 'revenue'
  | 'cost'
  | 'margin'
  | 'net'
  | 'users'
  | 'conversations'
  | 'tokens'

export const METRIC_COLORS: Record<ChartMetric, string> = {
  /** Gateway money actually received — green, same token StatCard uses for it. */
  revenue: 'var(--positive)',
  /** Money paid upstream — red. */
  cost: 'var(--danger)',
  /** Margin — amber, visually "between" revenue and cost. */
  margin: 'var(--warning)',
  /** Net profit — the brand accent; the headline series. */
  net: 'var(--accent)',
  /** User growth — blue. */
  users: 'var(--info)',
  /** Conversation growth — the forest-green secondary accent (see the
   *  --accent-purple naming note in globals.css; the name is legacy, the
   *  value is green and distinct from --info on both surfaces). */
  conversations: 'var(--accent-purple)',
  /** Token volume — the second accent stop; never on the same axis as `net`. */
  tokens: 'var(--accent-2)',
}

export function metricColor(metric: ChartMetric): string {
  return METRIC_COLORS[metric]
}

/** Horizontal gridlines — the hairline border token in both themes. */
export const CHART_GRID_COLOR = 'var(--border)'

/** The zero line when the scale spans negative values — one step stronger
 *  than the grid so "below zero" is unmissable. */
export const CHART_ZERO_COLOR = 'var(--border-strong)'

/** Tooltip surface tokens, matching the elevated-card look of the panel. */
export const CHART_TOOLTIP_BG = 'var(--bg-elevated)'
export const CHART_TOOLTIP_BORDER = 'var(--border-strong)'
