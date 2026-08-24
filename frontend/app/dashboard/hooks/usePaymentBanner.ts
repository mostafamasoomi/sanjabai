import { useState, useEffect } from 'react'
import type { ReadonlyURLSearchParams } from 'next/navigation'

/* ═══════════════════════════════════════════════════════════════════════════
   Payment-return banner. The gateway callback redirects here with
   ?subscription=active on a successful plan purchase and ?payment=failed on
   a decline/cancel (backend/payment_endpoints.py). Nothing used to read
   those params, so a real charge landed with zero feedback. Split out of
   page.tsx verbatim -- no behaviour change, including the URL-strip step.
   ═══════════════════════════════════════════════════════════════════════════ */

export function usePaymentBanner(searchParams: ReadonlyURLSearchParams) {
  const [paymentBanner, setPaymentBanner] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    const payment = searchParams.get('payment')
    const subscription = searchParams.get('subscription')
    let banner: { ok: boolean; text: string } | null = null
    if (subscription === 'active') {
      banner = { ok: true, text: 'اشتراک شما با موفقیت فعال شد.' }
    } else if (payment === 'success') {
      banner = { ok: true, text: 'پرداخت با موفقیت انجام شد.' }
    } else if (payment === 'failed') {
      banner = { ok: false, text: 'پرداخت ناموفق بود یا لغو شد. مبلغی از حساب شما کسر نشده است.' }
    } else if (payment === 'error') {
      banner = { ok: false, text: 'خطایی در پردازش پرداخت رخ داد. اگر مبلغی کسر شده باشد، به‌زودی بازمی‌گردد.' }
    }
    if (banner) {
      setPaymentBanner(banner)
      // Strip the params so a refresh (or back/forward) does not replay the
      // banner over a payment the user already saw the result of.
      const url = new URL(window.location.href)
      url.searchParams.delete('payment')
      url.searchParams.delete('subscription')
      window.history.replaceState(null, '', url.pathname + url.search + url.hash)
    }
  }, [searchParams])

  return { paymentBanner, setPaymentBanner }
}
