import { useState } from 'react'
import { apiFetch } from '@/lib/apiFetch'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { useTopupFlowStrings } from './useTopupFlow.strings'
import { MIN_TOPUP, MAX_TOPUP } from '../walletHelpers'

// Wallet top-up (preset/custom amount -> confirm -> gateway redirect) and
// credit-package purchase. Kept as one hook because both are the same
// shape of mutation -- apiFetch a POST that returns a gateway `url` and
// redirect to it -- and both are page-wide payment-initiation state, not
// presentational.
export function useTopupFlow(token: string | null) {
  const lang = useLang()
  const s = useTopupFlowStrings(lang)
  const f = fmt(lang)
  const [busy, setBusy] = useState(false)
  const [topupAmount, setTopupAmount] = useState('')
  const [selectedPreset, setSelectedPreset] = useState<number | null>(100_000)
  const [showConfirm, setShowConfirm] = useState(false)
  const [purchasingPkgId, setPurchasingPkgId] = useState<string | null>(null)

  const effectiveAmount = (selectedPreset ?? parseInt(topupAmount)) || 0

  const handlePreset = (val: number) => {
    setSelectedPreset(val)
    setTopupAmount('')
  }

  const handleCustomAmount = (v: string) => {
    setSelectedPreset(null)
    setTopupAmount(v)
  }

  const initiateTopup = () => {
    const amount = effectiveAmount
    if (!amount || amount < MIN_TOPUP) return toast(s.minAmount(f.num(MIN_TOPUP)), 'error')
    if (amount > MAX_TOPUP) return toast(s.maxAmount(f.num(MAX_TOPUP)), 'error')
    setShowConfirm(true)
  }

  const confirmTopup = async () => {
    if (!token) return
    setShowConfirm(false)
    setBusy(true)
    try {
      // /api/wallet/topup was dead (required a payment_order_id the
      // frontend never sent and queried a column that no longer exists) and
      // is being removed. The gateway entry point is /payment/request,
      // which returns { authority, url, amount } -- not payment_url -- and
      // there is no synchronous "credit applied" branch: the wallet is only
      // credited later, atomically, when the gateway calls back
      // (backend/payment_endpoints.py:26-57, :211).
      const res = await apiFetch('/api/payment/request', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: effectiveAmount, description: s.walletTopupDescription }),
      })
      const data = await res.json()
      if (res.ok && data.url) {
        toast(s.redirecting, 'info')
        window.location.href = data.url
      } else {
        toast(data.detail || s.topupError, 'error')
      }
    } catch {
      toast(s.serverError, 'error')
    } finally {
      setBusy(false)
    }
  }

  const handlePurchase = async (pkgId: string) => {
    if (!token || purchasingPkgId) return
    setPurchasingPkgId(pkgId)
    try {
      const res = await apiFetch('/api/credit-package/checkout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ package_id: pkgId }),
      })
      const data = await res.json()
      if (res.ok && data.url) {
        toast(s.redirecting, 'info')
        window.location.href = data.url
      } else {
        toast(data.detail || s.purchaseError, 'error')
      }
    } catch {
      toast(s.serverError, 'error')
    } finally {
      setPurchasingPkgId(null)
    }
  }

  return {
    busy,
    topupAmount,
    selectedPreset,
    showConfirm,
    setShowConfirm,
    purchasingPkgId,
    effectiveAmount,
    handlePreset,
    handleCustomAmount,
    initiateTopup,
    confirmTopup,
    handlePurchase,
  }
}
