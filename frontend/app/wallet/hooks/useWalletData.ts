import { useState, useEffect, useCallback } from 'react'
import { toast } from '@/components/ui'
import type { LedgerEntry, PaymentRecord, CreditPackage } from '../walletTypes'

// Fetches wallet balance, ledger, payment history, credit packages, and the
// live per-model output-token rate table (for the "≈ N tokens" estimate on
// model-labeled credit packages -- server-authoritative, never hardcoded).
// Kept as one hook because all four/five requests are fired together and
// share the same loading/refreshing lifecycle.
export function useWalletData(token: string | null) {
  const [balance, setBalance] = useState<number | null>(null)
  const [ledger, setLedger] = useState<LedgerEntry[]>([])
  const [payments, setPayments] = useState<PaymentRecord[]>([])
  const [creditPackages, setCreditPackages] = useState<CreditPackage[]>([])
  const [modelOutputRates, setModelOutputRates] = useState<Record<string, number>>({})

  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchData = useCallback(
    async (silent = false) => {
      if (!token) return
      if (!silent) setLoading(true)
      else setRefreshing(true)

      const headers = { Authorization: `Bearer ${token}` }
      try {
        const [walletRes, ledgerRes, payRes, pkgRes] = await Promise.all([
          fetch('/api/wallet', { headers }),
          fetch('/api/wallet/ledger', { headers }),
          fetch('/api/payment/history', { headers }),
          fetch('/api/credit-packages', { headers }),
        ])
        const [wallet, ledgerData, payData, pkgData] = await Promise.all([
          walletRes.ok ? walletRes.json() : null,
          ledgerRes.ok ? ledgerRes.json() : null,
          payRes.ok ? payRes.json() : null,
          pkgRes.ok ? pkgRes.json() : null,
        ])
        if (wallet) setBalance(wallet.balance ?? 0)
        if (ledgerData) setLedger(Array.isArray(ledgerData) ? ledgerData : [])
        if (payData) setPayments(Array.isArray(payData) ? payData : [])
        if (pkgData) setCreditPackages(Array.isArray(pkgData) ? pkgData : [])

        try {
          const catRes = await fetch('/api/catalog/models')
          if (catRes.ok) {
            const catData = await catRes.json()
            const rates: Record<string, number> = {}
            for (const m of catData.data || []) {
              const rate = m?.pricing?.outputPerMillion
              if (typeof rate === 'number' && rate > 0) {
                if (m.id) rates[m.id] = rate
                if (m.providerModelId) rates[m.providerModelId] = rate
              }
            }
            setModelOutputRates(rates)
          }
        } catch {}
      } catch {
        if (!silent) toast('خطا در دریافت اطلاعات', 'error')
      } finally {
        setLoading(false)
        setRefreshing(false)
      }
    },
    [token],
  )

  useEffect(() => {
    if (!token) {
      setLoading(false)
      return
    }
    fetchData()
  }, [token, fetchData])

  return { balance, ledger, payments, creditPackages, modelOutputRates, loading, refreshing, fetchData }
}
