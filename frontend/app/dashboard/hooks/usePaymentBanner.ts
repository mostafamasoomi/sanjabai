import { useState, useEffect } from 'react'
import type { ReadonlyURLSearchParams } from 'next/navigation'
import { useLang } from '@/components/LanguageToggle'
import { usePaymentBannerStrings } from './usePaymentBanner.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Payment-return banner. The gateway callback redirects here with
   ?payment=success on a successful credit-package purchase and
   ?payment=failed on a decline/cancel (backend/payment_endpoints.py).
   Nothing used to read those params, so a real charge landed with zero
   feedback. Split out of page.tsx verbatim -- no behaviour change,
   including the URL-strip step.

   The ?subscription=active branch that used to live here is gone: the
   plan/subscription concept is retired, subscription checkout no longer
   exists, and the gateway now redirects a completed credit-package payment
   straight to /wallet?payment=success instead -- this page never sees a
   `subscription` query param for a real purchase anymore.
   ═══════════════════════════════════════════════════════════════════════════ */

export function usePaymentBanner(searchParams: ReadonlyURLSearchParams) {
  // Itself a hook (called from DashboardPage) -- safe to read the language
  // directly rather than take it as a parameter, see the i18n spec note.
  const lang = useLang()
  const s = usePaymentBannerStrings(lang)
  const [paymentBanner, setPaymentBanner] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    const payment = searchParams.get('payment')
    let banner: { ok: boolean; text: string } | null = null
    if (payment === 'success') {
      banner = { ok: true, text: s.paymentSuccess }
    } else if (payment === 'failed') {
      banner = { ok: false, text: s.paymentFailed }
    } else if (payment === 'error') {
      banner = { ok: false, text: s.paymentError }
    }
    if (banner) {
      setPaymentBanner(banner)
      // Strip the param so a refresh (or back/forward) does not replay the
      // banner over a payment the user already saw the result of.
      const url = new URL(window.location.href)
      url.searchParams.delete('payment')
      window.history.replaceState(null, '', url.pathname + url.search + url.hash)
    }
  }, [searchParams, s])

  return { paymentBanner, setPaymentBanner }
}
