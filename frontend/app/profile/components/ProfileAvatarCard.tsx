'use client'

import { useRef } from 'react'
import { Icon } from '@/components/ui/Icon'
import { faNum, faPrice, toFaDigits } from '@/lib/format'

type ProfileAvatarCardProps = {
  isFa: boolean
  avatarUrl: string
  avatarUploading: boolean
  handleAvatarUpload: (e: React.ChangeEvent<HTMLInputElement>) => void
  userInitial: string
  displayName: string
  bio: string
  user: any
  balance: number | null
  usage: any
  statsError: boolean
}

export default function ProfileAvatarCard({
  isFa, avatarUrl, avatarUploading, handleAvatarUpload, userInitial, displayName, bio, user,
  balance, usage, statsError,
}: ProfileAvatarCardProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)

  return (
    <div className="card profile-avatar-card">
      <div className="profile-avatar-section">
        <div
          className="profile-avatar cursor-pointer relative"
          onClick={() => fileInputRef.current?.click()}
        >
          {avatarUrl ? (
            <img
              src={avatarUrl}
              alt="avatar"
              style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '50%' }}
            />
          ) : (
            <span className="profile-avatar-letter">{userInitial}</span>
          )}
          <div style={{
            position: 'absolute', bottom: 0, right: 0,
            background: 'var(--accent-fill)', borderRadius: '50%',
            width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
            border: '2px solid var(--bg-card)',
          }}>
            {avatarUploading ? (
              <div className="apikeys-spinner" style={{ width: 12, height: 12 }} />
            ) : (
              <Icon name="camera" size={12} style={{ color: 'var(--text-on-accent)' }} />
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleAvatarUpload}
          />
        </div>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
            {displayName || user?.email || (isFa ? 'کاربر' : 'User')}
          </h2>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            {isFa
              ? `عضو از ${user?.created_at ? toFaDigits(new Date(user.created_at).toLocaleDateString('fa-IR', { year: 'numeric', month: 'long' })) : '—'}`
              : `Member since ${user?.created_at ? new Date(user.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long' }) : '—'}`
            }
          </p>
          {bio && <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>{bio}</p>}
        </div>
      </div>

      <div className="profile-stats-grid">
        <div className="profile-stat-card">
          <Icon name="wallet" size={18} className="text-accent" />
          <div>
            <span className="profile-stat-label">{isFa ? 'موجودی' : 'Balance'}</span>
            <span className="profile-stat-value text-gradient">
              {/* balance is raw integer TOMAN. The old English branch both
                  bypassed faPrice and mislabeled toman as "IRR" (Rial) — a
                  10x-class currency bug. Always go through faPrice. */}
              {balance === null ? '—' : faPrice(balance)}
            </span>
          </div>
        </div>
        <div className="profile-stat-card">
          <Icon name="chart" size={18} className="text-positive" />
          <div>
            <span className="profile-stat-label">{isFa ? 'مصرف ماهانه' : 'Monthly usage'}</span>
            <span className="profile-stat-value">
              {/* Token counts go through faNum in both branches — the old
                  English branch used toLocaleString, which returns Latin
                  digits on the production small-icu runtime. */}
              {!usage?.monthly
                ? '—'
                : isFa
                  ? `${faNum(usage.monthly.inp + usage.monthly.out || 0)} توکن`
                  : `${faNum(usage.monthly.inp + usage.monthly.out || 0)} tokens`}
            </span>
          </div>
        </div>
        <div className="profile-stat-card">
          <Icon name="mail" size={18} style={{ color: 'var(--info)' }} />
          <div>
            <span className="profile-stat-label">{isFa ? 'ایمیل' : 'Email'}</span>
            <span className="profile-stat-value">{user?.email || '—'}</span>
          </div>
        </div>
      </div>
      {statsError && (
        <p style={{ fontSize: 12, color: 'var(--danger)', marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icon name="warning" size={13} />
          {isFa ? 'خطا در بارگذاری موجودی و آمار مصرف.' : 'Failed to load balance and usage stats.'}
        </p>
      )}
    </div>
  )
}
