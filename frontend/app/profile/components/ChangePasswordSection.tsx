import { Icon } from '@/components/ui/Icon'

type ChangePasswordSectionProps = {
  isFa: boolean
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
  isFa, currentPassword, setCurrentPassword, newPassword, setNewPassword,
  confirmPassword, setConfirmPassword, changingPassword, handleChangePassword,
}: ChangePasswordSectionProps) {
  return (
    <div className="card profile-section-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="lock" size={16} className="text-accent" />
        <h2 className="card-title">
          {isFa ? 'تغییر رمز عبور' : 'Change Password'}
        </h2>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div className="profile-input-group">
          <label className="profile-input-label">{isFa ? 'رمز عبور فعلی' : 'Current Password'}</label>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            placeholder={isFa ? 'رمز عبور فعلی' : 'Current password'}
            className="input"
          />
        </div>
        <div className="profile-input-group">
          <label className="profile-input-label">{isFa ? 'رمز عبور جدید' : 'New Password'}</label>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder={isFa ? 'حداقل ۸ کاراکتر' : 'At least 8 characters'}
            className="input"
          />
        </div>
        <div className="profile-input-group">
          <label className="profile-input-label">{isFa ? 'تکرار رمز عبور جدید' : 'Confirm New Password'}</label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder={isFa ? 'تکرار رمز عبور جدید' : 'Confirm new password'}
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
          {isFa ? 'تغییر رمز عبور' : 'Change Password'}
        </button>
      </div>
    </div>
  )
}
