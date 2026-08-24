import { Icon } from '@/components/ui/Icon'

type AppearanceSectionProps = {
  isFa: boolean
  theme: string
  setTheme: (v: string) => void
  language: string
  setLanguage: (v: string) => void
}

export default function AppearanceSection({ isFa, theme, setTheme, language, setLanguage }: AppearanceSectionProps) {
  return (
    <div className="card profile-section-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="palette" size={16} className="text-accent" />
        <h2 className="card-title">
          {isFa ? 'ظاهر و زبان' : 'Appearance & Language'}
        </h2>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {/* Theme toggle */}
        <div className="profile-toggle-row">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon name="moon" size={16} className="text-muted" />
            <div>
              <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
                {isFa ? 'حالت تاریک' : 'Dark Mode'}
              </span>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                {isFa ? 'استفاده از تم تاریک' : 'Use dark theme'}
              </p>
            </div>
          </div>
          <button
            className={`profile-toggle ${theme === 'dark' ? 'active' : ''}`}
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            role="switch"
            aria-checked={theme === 'dark'}
          >
            <span className="profile-toggle-knob" />
          </button>
        </div>

        {/* Language selector */}
        <div className="profile-toggle-row">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon name="globe" size={16} className="text-muted" />
            <div>
              <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
                {isFa ? 'زبان / Language' : 'Language / زبان'}
              </span>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                {isFa ? 'فارسی یا انگلیسی' : 'Persian or English'}
              </p>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              className={`btn btn-sm ${language === 'fa' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setLanguage('fa')}
              style={{ fontSize: 12, padding: '4px 12px' }}
            >
              فارسی
            </button>
            <button
              className={`btn btn-sm ${language === 'en' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setLanguage('en')}
              style={{ fontSize: 12, padding: '4px 12px' }}
            >
              English
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
