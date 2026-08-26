import { useState, useEffect } from 'react'
import type { ReadonlyURLSearchParams } from 'next/navigation'
import { useLang } from '@/components/LanguageToggle'
import { usePaymentBannerStrings } from './usePaymentBanner.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Payment-return banner. The gateway callback redirects here with
   ?subscription=active on a successful plan purchase and ?payment=failed on
   a decline/cancel (backend/payment_endpoints.py). Nothing used to read
   those params, so a real charge landed with zero feedback. Split out of
   page.tsx verbatim -- no behaviour change, including the URL-strip step.
   ═══════════════════════════════════════════════════════════════════════════ */

export function usePaymentBanner(searchParams: ReadonlyURLSearchParams) {
  // Itself a hook (called from DashboardPage) -- safe to read the language
  // directly rather than take it as a parameter, see the i18n spec note.
  const lang = useLang()
  const s = usePaymentBannerStrings(lang)
  const [paymentBanner, setPaymentBanner] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    const payment = searchParams.get('payment')
    const subscription = searchParams.get('subscription')
    let banner: { ok: boolean; text: string } | null = null
    if (subscription === 'active') {
      banner = { ok: true, text: s.subscriptionActive }
    } else if (payment === 'success') {
      banner = { ok: true, text: s.paymentSuccess }
    } else if (payment === 'failed') {
      banner = { ok: false, text: s.paymentFailed }
    } else if (payment === 'error') {
      banner = { ok: false, text: s.paymentError }
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
  }, [searchParams, s])

  return { paymentBanner, setPaymentBanner }
}
