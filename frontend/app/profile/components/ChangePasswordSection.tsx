'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { changePasswordSectionStrings } from './ChangePasswordSection.strings'

type ChangePasswordSectionProps = {
  currentPassword: string
  setCurrentPassword: (v: string) => void
  newPassword: string
  setNewPassword: (v: string) => void
  confirmPassword: string
  setConfirmPassword: (v: string) => void
  changingPassword: boolean
  handleChangePassword: () => void
}

export default function ChangePasswordSection({
  currentPassword, setCurrentPassword, newPassword, setNewPassword,
  confirmPassword, setConfirmPassword, changingPassword, handleChangePassword,
}: ChangePasswordSectionProps) {
  const lang = useLang()
  const s = changePasswordSectionStrings(lang)

  return (
    <div className="card profile-section-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="lock" size={16} className="text-accent" />
        <h2 className="card-title">
          {s.title}
        </h2>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div className="profile-input-group">
          <label className="profile-input-label">{s.current}</label>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            placeholder={s.currentPlaceholder}
            className="input"
          />
        </div>
        <div className="profile-input-group">
          <label className="profile-input-label">{s.newPassword}</label>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder={s.newPasswordPlaceholder}
            className="input"
          />
        </div>
        <div className="profile-input-group">
          <label className="profile-input-label">{s.confirm}</label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder={s.confirmPlaceholder}
            className="input"
          />
        </div>
        <button
          onClick={handleChangePassword}
          disabled={changingPassword || !currentPassword || !newPassword}
          className="btn btn-primary"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, alignSelf: 'flex-start' }}
        >
          {changingPassword ? (
            <span className="apikeys-spinner" />
          ) : (
            <Icon name="lock" size={14} />
          )}
          {s.submit}
        </button>
      </div>
    </div>
  )
}
