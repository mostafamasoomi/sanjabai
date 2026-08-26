import { useState, useCallback, type Dispatch, type SetStateAction } from 'react'
import { apiFetch } from '@/lib/apiFetch'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { useBillingSettingsStrings } from './useBillingSettings.strings'
import type { BillingSettings } from '../types'

/* ═══════════════════════════════════════════════════════════════════════════
   PAYG toggle + hard-limit editing. Split out of page.tsx verbatim -- no
   behaviour change. Both mutations go through apiFetch (CSRF) and update the
   shared billingSettings state owned by useDashboardData.
   ═══════════════════════════════════════════════════════════════════════════ */

export function useBillingSettings(
  token: string | null,
  billingSettings: BillingSettings,
  setBillingSettings: Dispatch<SetStateAction<BillingSettings>>
) {
  // This hook is itself a hook (called from DashboardPage), so it is safe to
  // read the language directly rather than take it as a parameter -- see the
  // note in the i18n spec on hook files.
  const lang = useLang()
  const s = useBillingSettingsStrings(lang)
  const [paygLoading, setPaygLoading] = useState(false)
  const [showHardLimitInput, setShowHardLimitInput] = useState(false)
  const [hardLimitValue, setHardLimitValue] = useState('')
  const [hardLimitLoading, setHardLimitLoading] = useState(false)

  /* ─── Toggle PAYG ─── */
  const togglePayg = useCallback(async () => {
    if (!token || !billingSettings) return
    setPaygLoading(true)
    try {
      const res = await apiFetch('/api/billing/settings', {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ payg_enabled: !billingSettings.payg_enabled }),
      })
      if (res.ok) {
        setBillingSettings((prev) => prev ? { ...prev, payg_enabled: !prev.payg_enabled } : prev)
        toast(billingSettings.payg_enabled ? s.paygDisabled : s.paygEnabled, 'success')
      } else {
        toast(s.settingsError, 'error')
      }
    } catch {
      toast(s.serverError, 'error')
    } finally {
      setPaygLoading(false)
    }
  }, [token, billingSettings, setBillingSettings, s])

  /* ─── Set Hard Limit ─── */
  const setHardLimit = useCallback(async () => {
    if (!token) return
    const parsed = parseInt(hardLimitValue, 10)
    if (isNaN(parsed) || parsed < 0) {
      toast(s.invalidAmount, 'error')
      return
    }
    setHardLimitLoading(true)
    try {
      const res = await apiFetch('/api/billing/settings', {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ payg_hard_limit: parsed }),
      })
      if (res.ok) {
        setBillingSettings((prev) => prev ? { ...prev, payg_hard_limit: parsed } : prev)
        setShowHardLimitInput(false)
        setHardLimitValue('')
        toast(s.hardLimitSet, 'success')
      } else {
        toast(s.hardLimitError, 'error')
      }
    } catch {
      toast(s.serverError, 'error')
    } finally {
      setHardLimitLoading(false)
    }
  }, [token, hardLimitValue, setBillingSettings, s])

  return {
    paygLoading,
    showHardLimitInput,
    setShowHardLimitInput,
    hardLimitValue,
    setHardLimitValue,
    hardLimitLoading,
    togglePayg,
    setHardLimit,
  }
}
