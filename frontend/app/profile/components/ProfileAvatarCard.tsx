'use client'

import { useRef } from 'react'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { toFaDigits } from '@/lib/format'
import { profileAvatarCardStrings } from './ProfileAvatarCard.strings'
import type { ProfileUser } from '../types'

type ProfileAvatarCardProps = {
  avatarUrl: string
  avatarUploading: boolean
  handleAvatarUpload: (e: React.ChangeEvent<HTMLInputElement>) => void
  handleRemoveAvatar: () => void
  userInitial: string
  displayName: string
  bio: string
  user: ProfileUser | null
  balance: number | null
  usage: any
  statsError: boolean
}

export default function ProfileAvatarCard({
  avatarUrl, avatarUploading, handleAvatarUpload, handleRemoveAvatar, userInitial, displayName, bio, user,
  balance, usage, statsError,
}: ProfileAvatarCardProps) {
  const lang = useLang()
  const s = profileAvatarCardStrings(lang)
  const f = fmt(lang)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Member-since only needs year+month, one granularity coarser than
  // fmt(lang).date() — kept as a local format rather than routed through
  // f.date so this doesn't start showing a day-of-month it never showed.
  const memberSince = user?.created_at
    ? (lang === 'fa'
        ? toFaDigits(new Date(user.created_at).toLocaleDateString('fa-IR', { year: 'numeric', month: 'long' }))
        : new Date(user.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long' }))
    : '—'

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
          {avatarUrl && (
            // Positioned at the opposite corner from the camera badge, and
            // -- critically -- stops event propagation first, before the
            // handler runs. The whole circle above is a click target that
            // opens the file picker; without stopPropagation a click here
            // would both remove the avatar AND open the file dialog underneath it.
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                handleRemoveAvatar()
              }}
              disabled={avatarUploading}
              aria-label={s.removeAvatar}
              title={s.removeAvatar}
              style={{
                position: 'absolute', insetBlockStart: 0, insetInlineEnd: 0,
                background: 'var(--danger)', borderRadius: '50%',
                width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center',
                border: '2px solid var(--bg-card)', cursor: avatarUploading ? 'default' : 'pointer',
                opacity: avatarUploading ? 0.6 : 1, padding: 0,
              }}
            >
              <Icon name="trash" size={11} style={{ color: 'var(--text-on-accent)' }} />
            </button>
          )}
        </div>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
            {displayName || user?.email || s.user}
          </h2>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            {s.memberSince(memberSince)}
          </p>
          {bio && <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>{bio}</p>}
        </div>
      </div>

      <div className="profile-stats-grid">
        <div className="profile-stat-card">
          <Icon name="wallet" size={18} className="text-accent" />
          <div>
            <span className="profile-stat-label">{s.balance}</span>
            <span className="profile-stat-value text-gradient">
              {/* balance is raw integer TOMAN. The old English branch both
                  bypassed faPrice and mislabeled toman as "IRR" (Rial) — a
                  10x-class currency bug. Always go through f.price. */}
              {balance === null ? '—' : f.price(balance)}
            </span>
          </div>
        </div>
        <div className="profile-stat-card">
          <Icon name="chart" size={18} className="text-positive" />
          <div>
            <span className="profile-stat-label">{s.monthlyUsage}</span>
            <span className="profile-stat-value">
              {!usage?.monthly
                ? '—'
                : s.tokens(f.num(usage.monthly.inp + usage.monthly.out || 0))}
            </span>
          </div>
        </div>
        <div className="profile-stat-card">
          <Icon name="mail" size={18} style={{ color: 'var(--info)' }} />
          <div>
            <span className="profile-stat-label">{s.email}</span>
            <span className="profile-stat-value">{user?.email || '—'}</span>
          </div>
        </div>
      </div>
      {statsError && (
        <p style={{ fontSize: 12, color: 'var(--danger)', marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icon name="warning" size={13} />
          {s.statsError}
        </p>
      )}
    </div>
  )
}
