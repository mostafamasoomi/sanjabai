import { Icon } from '@/components/ui/Icon'

type NotificationsSectionProps = {
  isFa: boolean
  emailNotif: boolean
  setEmailNotif: (v: boolean) => void
  telegramNotif: boolean
  setTelegramNotif: (v: boolean) => void
}

export default function NotificationsSection({
  isFa, emailNotif, setEmailNotif, telegramNotif, setTelegramNotif,
}: NotificationsSectionProps) {
  return (
    <div className="card profile-section-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="bell" size={16} className="text-accent" />
        <h2 className="card-title">
          {isFa ? 'اعلان‌ها' : 'Notifications'}
        </h2>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <div className="profile-toggle-row">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon name="mail" size={16} className="text-muted" />
            <div>
              <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
                {isFa ? 'اعلان ایمیلی' : 'Email Notifications'}
              </span>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                {isFa ? 'دریافت اعلانها از طریق ایمیل' : 'Receive notifications via email'}
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
                {isFa ? 'اعلان تلگرامی' : 'Telegram Notifications'}
              </span>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                {isFa ? 'دریافت اعلانها از طریق ربات تلگرام' : 'Receive notifications via Telegram bot'}
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
