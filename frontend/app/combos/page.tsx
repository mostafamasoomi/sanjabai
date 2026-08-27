'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { dirFor } from '@/lib/i18n'
import ComboManager from './components/ComboManager'
import { comboStrings } from './components/ComboManager.strings'

/* ═══════════════════════════════════════════════════════════════
   /combos — manage the user's own ordered model combos.

   This file owns only the auth gate and the page chrome; the list,
   the editor and every call to /api/me/combos live in components/.
   ═══════════════════════════════════════════════════════════════ */

export default function CombosPage() {
  const { user, token, loading: authLoading } = useAuth()
  const router = useRouter()
  const lang = useLang()
  const s = comboStrings(lang)

  useEffect(() => {
    if (!authLoading && !user) router.replace('/login')
  }, [authLoading, user, router])

  if (authLoading || !user) {
    return (
      <div style={{ maxWidth: 860, margin: '0 auto', padding: '0 16px' }}>
        <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>{s.authLoading}</p>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: '0 16px' }} dir={dirFor(lang)}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
        <span className="card-icon">
          <Icon name="models" size={18} />
        </span>
        <div>
          <h1 className="page-title">{s.pageTitle}</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 2, lineHeight: 1.7 }}>
            {s.pageSubtitle}
          </p>
        </div>
      </div>

      <ComboManager token={token} />
    </div>
  )
}
