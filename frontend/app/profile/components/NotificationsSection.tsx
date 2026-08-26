'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { notificationsSectionStrings } from './NotificationsSection.strings'

type NotificationsSectionProps = {
  emailNotif: boolean
  setEmailNotif: (v: boolean) => void
  telegramNotif: boolean
  setTelegramNotif: (v: boolean) => void
}

export default function NotificationsSection({
  emailNotif, setEmailNotif, telegramNotif, setTelegramNotif,
}: NotificationsSectionProps) {
  const lang = useLang()
  const s = notificationsSectionStrings(lang)

  return (
    <div className="card profile-section-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="bell" size={16} className="text-accent" />
        <h2 className="card-title">
          {s.title}
        </h2>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <div className="profile-toggle-row">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon name="mail" size={16} className="text-muted" />
            <div>
              <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
                {s.email}
              </span>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                {s.emailHint}
              </p>
            </div>
          </div>
          <button
            className={`profile-toggle ${emailNotif ? 'active' : ''}`}
            onClick={() => setEmailNotif(!emailNotif)}
            role="switch"
            aria-checked={emailNotif}
          >
            <span className="profile-toggle-knob" />
          </button>
        </div>
        <div className="profile-toggle-row">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon name="send" size={16} className="text-muted" />
            <div>
              <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
                {s.telegram}
              </span>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                {s.telegramHint}
              </p>
            </div>
          </div>
          <button
            className={`profile-toggle ${telegramNotif ? 'active' : ''}`}
            onClick={() => setTelegramNotif(!telegramNotif)}
            role="switch"
            aria-checked={telegramNotif}
          >
            <span className="profile-toggle-knob" />
          </button>
        </div>
      </div>
    </div>
  )
}
