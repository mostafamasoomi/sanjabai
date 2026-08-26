'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { InfoRow } from './InfoRow'
import { accountInfoCardStrings } from './AccountInfoCard.strings'
import type { UserProfile } from '../types'

/* ═══════════════════════════════════════════════════════════════
   Account Info
   ═══════════════════════════════════════════════════════════════ */

export function AccountInfoCard({
  profile,
  onManageAccount,
}: {
  profile: UserProfile | null
  onManageAccount: () => void
}) {
  const lang = useLang()
  const s = accountInfoCardStrings(lang)
  const f = fmt(lang)

  return (
    <div className="card dash-span-4">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
        <span className="text-[var(--accent)]">
          <Icon name="profile" size={18} />
        </span>
        <h2 className="card-title">{s.title}</h2>
      </div>
      <div className="flex flex-col gap-3">
        <InfoRow icon="profile" label={s.email} value={profile?.email || '—'} />
        {profile?.username && <InfoRow icon="profile" label={s.username} value={profile.username} />}
        {profile?.phone && <InfoRow icon="notification" label={s.phone} value={profile.phone} />}
        <InfoRow icon="security" label={s.status} value={profile?.is_active ? s.active : s.inactive} />
        <InfoRow
          icon="dashboard"
          label={s.joined}
          value={profile?.created_at ? f.date(profile.created_at) : '—'}
        />
      </div>
      <div className="divider" style={{ margin: '1rem 0' }} />
      <button
        className="btn btn-sm"
        onClick={onManageAccount}
        style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.375rem' }}
      >
        <Icon name="settings" size={14} />
        {s.manage}
      </button>
    </div>
  )
}
