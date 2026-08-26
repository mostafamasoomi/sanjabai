'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { TIMEZONES } from '../types'
import { personalInfoSectionStrings } from './PersonalInfoSection.strings'

type PersonalInfoSectionProps = {
  displayName: string
  setDisplayName: (v: string) => void
  bio: string
  setBio: (v: string) => void
  timezone: string
  setTimezone: (v: string) => void
}

export default function PersonalInfoSection({
  displayName, setDisplayName, bio, setBio, timezone, setTimezone,
}: PersonalInfoSectionProps) {
  const lang = useLang()
  const s = personalInfoSectionStrings(lang)
  const f = fmt(lang)

  return (
    <div className="card profile-section-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="user" size={16} className="text-accent" />
        <h2 className="card-title">
          {s.title}
        </h2>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="profile-input-group">
          <label className="profile-input-label">{s.displayName}</label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder={s.displayNamePlaceholder}
            className="input"
            maxLength={100}
          />
        </div>
        <div className="profile-input-group">
          <label className="profile-input-label">{s.bio}</label>
          <textarea dir={lang === 'fa' ? 'rtl' : 'ltr'}
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            placeholder={s.bioPlaceholder}
            className="input"
            rows={3}
            maxLength={500}
            style={{ resize: 'vertical', minHeight: 80 }}
          />
          <span style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'left', display: 'block' }}>
            {f.num(bio.length)}/{f.num(500)}
          </span>
        </div>
        <div className="profile-input-group">
          <label className="profile-input-label">{s.timezone}</label>
          <select
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            className="input"
            style={{ appearance: 'auto' }}
          >
            {TIMEZONES.map((tz) => (
              <option key={tz.value} value={tz.value}>{lang === 'fa' ? tz.label_fa : tz.label_en}</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  )
}
