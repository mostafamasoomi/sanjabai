import { useState, useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import type { PaymentBannerState } from '../walletTypes'

// Payment-return banner. The gateway callback redirects here with
// ?payment=success after a credit is applied, ?payment=failed on a
// decline/cancel, and ?payment=error when the callback itself faulted
// (backend/payment_endpoints.py + app/api/payment/callback/route.ts).
// Nothing used to read these, so a real charge landed with no feedback.
//
// State stores `kind`, not rendered text -- PaymentBanner.tsx looks the
// fa/en copy up at render time (usePaymentBanner.strings.ts) so the banner
// still reads correctly if the user flips the language toggle while it's
// showing, instead of freezing whatever language was active on redirect.
export function usePaymentBanner() {
  const searchParams = useSearchParams()
  const [paymentBanner, setPaymentBanner] = useState<PaymentBannerState>(null)

  useEffect(() => {
    const payment = searchParams.get('payment')
    let banner: PaymentBannerState = null
    if (payment === 'success') {
      banner = { ok: true, kind: 'success' }
    } else if (payment === 'failed') {
      banner = { ok: false, kind: 'failed' }
    } else if (payment === 'error') {
      banner = { ok: false, kind: 'error' }
    }
    if (banner) {
      setPaymentBanner(banner)
      // Strip the param so a refresh does not replay the banner.
      const url = new URL(window.location.href)
      url.searchParams.delete('payment')
      window.history.replaceState(null, '', url.pathname + url.search + url.hash)
    }
  }, [searchParams])

  return { paymentBanner, setPaymentBanner }
}
