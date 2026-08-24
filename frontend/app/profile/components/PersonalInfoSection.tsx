import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { TIMEZONES } from '../types'

type PersonalInfoSectionProps = {
  isFa: boolean
  displayName: string
  setDisplayName: (v: string) => void
  bio: string
  setBio: (v: string) => void
  timezone: string
  setTimezone: (v: string) => void
}

export default function PersonalInfoSection({
  isFa, displayName, setDisplayName, bio, setBio, timezone, setTimezone,
}: PersonalInfoSectionProps) {
  return (
    <div className="card profile-section-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="user" size={16} className="text-accent" />
        <h2 className="card-title">
          {isFa ? 'اطلاعات شخصی' : 'Personal Info'}
        </h2>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="profile-input-group">
          <label className="profile-input-label">{isFa ? 'نام نمایشی' : 'Display Name'}</label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder={isFa ? 'نام شما' : 'Your name'}
            className="input"
            maxLength={100}
          />
        </div>
        <div className="profile-input-group">
          <label className="profile-input-label">{isFa ? 'بیوگرافی' : 'Bio'}</label>
          <textarea dir="rtl"
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            placeholder={isFa ? 'درباره خودتان بنویسید...' : 'Tell us about yourself...'}
            className="input"
            rows={3}
            maxLength={500}
            style={{ resize: 'vertical', minHeight: 80 }}
          />
          <span style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'left', display: 'block' }}>
            {faNum(bio.length)}/۵۰۰
          </span>
        </div>
        <div className="profile-input-group">
          <label className="profile-input-label">{isFa ? 'منطقه زمانی' : 'Timezone'}</label>
          <select
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            className="input"
            style={{ appearance: 'auto' }}
          >
            {TIMEZONES.map((tz) => (
              <option key={tz.value} value={tz.value}>{tz.label}</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  )
}
