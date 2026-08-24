import { useState, useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import type { PaymentBannerState } from '../walletTypes'

// Payment-return banner. The gateway callback redirects here with
// ?payment=success after a credit is applied, ?payment=failed on a
// decline/cancel, and ?payment=error when the callback itself faulted
// (backend/payment_endpoints.py + app/api/payment/callback/route.ts).
// Nothing used to read these, so a real charge landed with no feedback.
export function usePaymentBanner() {
  const searchParams = useSearchParams()
  const [paymentBanner, setPaymentBanner] = useState<PaymentBannerState>(null)

  useEffect(() => {
    const payment = searchParams.get('payment')
    let banner: PaymentBannerState = null
    if (payment === 'success') {
      banner = { ok: true, text: 'پرداخت با موفقیت انجام شد و کیف پول شما شارژ شد.' }
    } else if (payment === 'failed') {
      banner = { ok: false, text: 'پرداخت ناموفق بود یا لغو شد. مبلغی از حساب شما کسر نشده است.' }
    } else if (payment === 'error') {
      banner = { ok: false, text: 'خطایی در پردازش پرداخت رخ داد. اگر مبلغی کسر شده باشد، به‌زودی بازمی‌گردد.' }
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
