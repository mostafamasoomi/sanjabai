/**
 * eNamad trust seal. Markup is exactly what enamad.ir's badge generator
 * issues for this site's id/Code — kept verbatim via dangerouslySetInnerHTML
 * (including the nonstandard `code` attribute on <img>) rather than
 * hand-converted to JSX, since enamad's own verification may depend on the
 * exact markup. `compact` shrinks it to sit inline in the hero trust row
 * instead of full size in the footer.
 */
export function EnamadBadge({ compact = false }: { compact?: boolean }) {
  return (
    <span
      className={compact ? 'lp-enamad lp-enamad--compact' : 'lp-enamad'}
      dangerouslySetInnerHTML={{
        __html:
          "<a referrerpolicy='origin' target='_blank' href='https://trustseal.enamad.ir/?id=7527649&Code=438FIkEWAO3ftUDcIFWbdnA9GyyRducv'><img referrerpolicy='origin' src='https://trustseal.enamad.ir/logo.aspx?id=7527649&Code=438FIkEWAO3ftUDcIFWbdnA9GyyRducv' alt='' style='cursor:pointer' code='438FIkEWAO3ftUDcIFWbdnA9GyyRducv'></a>",
      }}
    />
  )
}
