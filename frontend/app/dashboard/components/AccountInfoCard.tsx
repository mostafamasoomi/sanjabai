import { Icon } from '@/components/ui/Icon'
import { faDate } from '@/lib/format'
import { InfoRow } from './InfoRow'
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
  return (
    <div className="card dash-span-4">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
        <span className="text-[var(--accent)]">
          <Icon name="profile" size={18} />
        </span>
        <h2 className="card-title">اطلاعات حساب</h2>
      </div>
      <div className="flex flex-col gap-3">
        <InfoRow icon="profile" label="ایمیل" value={profile?.email || '—'} />
        {profile?.username && <InfoRow icon="profile" label="نام کاربری" value={profile.username} />}
        {profile?.phone && <InfoRow icon="notification" label="تلفن" value={profile.phone} />}
        <InfoRow icon="security" label="وضعیت" value={profile?.is_active ? 'فعال' : 'غیرفعال'} />
        <InfoRow
          icon="dashboard"
          label="تاریخ عضویت"
          value={profile?.created_at ? faDate(profile.created_at) : '—'}
        />
      </div>
      <div className="divider" style={{ margin: '1rem 0' }} />
      <button
        className="btn btn-sm"
        onClick={onManageAccount}
        style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.375rem' }}
      >
        <Icon name="settings" size={14} />
        مدیریت حساب
      </button>
    </div>
  )
}
