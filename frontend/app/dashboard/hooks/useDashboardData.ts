import { useState, useEffect, useCallback } from 'react'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { useDashboardDataStrings } from './useDashboardData.strings'
import type {
  UserProfile,
  Usage,
  LedgerEntry,
  ModelItem,
  Subscription,
  SubscriptionPlan,
  BillingSettings,
} from '../types'

/* ═══════════════════════════════════════════════════════════════════════════
   Fetches and holds all dashboard data: profile, usage, wallet balance,
   ledger, catalog models, subscription, subscription plan, and billing
   settings. Split out of page.tsx verbatim -- no behaviour change.
   ═══════════════════════════════════════════════════════════════════════════ */

export function useDashboardData(token: string | null, authLoading: boolean) {
  // Itself a hook (called from DashboardPage) -- safe to read the language
  // directly rather than take it as a parameter, see the i18n spec note.
  const lang = useLang()
  const s = useDashboardDataStrings(lang)
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [usage, setUsage] = useState<Usage | null>(null)
  const [balance, setBalance] = useState<number | null>(null)
  const [ledger, setLedger] = useState<LedgerEntry[]>([])
  const [models, setModels] = useState<ModelItem[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  // Subscription & Billing state
  const [subscription, setSubscription] = useState<Subscription>(null)
  const [subscriptionPlan, setSubscriptionPlan] = useState<SubscriptionPlan>(null)
  const [billingSettings, setBillingSettings] = useState<BillingSettings>(null)

  const fetchData = useCallback(async (isRefresh = false) => {
    if (!token) { setLoading(false); return }

    if (isRefresh) setRefreshing(true)
    else setLoading(true)

    const headers = { Authorization: `Bearer ${token}` }

    try {
      const [meRes, usageRes, walletRes, ledgerRes, modelsRes, subRes, billingRes] = await Promise.allSettled([
        fetch('/api/auth/me', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        fetch('/api/me/usage', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        fetch('/api/wallet', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        fetch('/api/wallet/ledger', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        // /api/models does not exist (404) -- the real catalog endpoint is
        // /catalog/models (the same one wallet uses). The 404 is why the
        // "N مدل در دسترس" quick-action read ۰ forever.
        fetch('/api/catalog/models', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        fetch('/api/subscription', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
        fetch('/api/billing/settings', { headers }).then((r) => r.ok ? r.json() : Promise.reject(r.status)),
      ])

      if (meRes.status === 'fulfilled') setProfile(meRes.value)
      if (usageRes.status === 'fulfilled') setUsage(usageRes.value)
      if (walletRes.status === 'fulfilled') setBalance(walletRes.value?.balance ?? 0)
      if (ledgerRes.status === 'fulfilled') setLedger(Array.isArray(ledgerRes.value) ? ledgerRes.value.slice(0, 10) : [])
      if (modelsRes.status === 'fulfilled') setModels(modelsRes.value?.data ?? [])
      if (subRes.status === 'fulfilled') {
        setSubscription(subRes.value?.subscription ?? null)
        setSubscriptionPlan(subRes.value?.plan ?? null)
      }
      if (billingRes.status === 'fulfilled') setBillingSettings(billingRes.value ?? null)

      const failed = [meRes, usageRes, walletRes, ledgerRes, modelsRes, subRes, billingRes].filter((r) => r.status === 'rejected')
      if (failed.length === 7) {
        toast(s.allFailed, 'error')
      } else if (failed.length > 0) {
        toast(s.partialFailed, 'info')
      }
    } catch {
      toast(s.serverError, 'error')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [token, s])

  useEffect(() => {
    if (!authLoading) fetchData()
  }, [authLoading, fetchData])

  return {
    profile,
    usage,
    balance,
    ledger,
    models,
    loading,
    refreshing,
    subscription,
    subscriptionPlan,
    billingSettings,
    setBillingSettings,
    fetchData,
  }
}
