'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { appearanceSectionStrings } from './AppearanceSection.strings'

type AppearanceSectionProps = {
  theme: string
  setTheme: (v: string) => void
  language: string
  setLanguage: (v: string) => void
}

/* The "language" here is the account's own stored preference
   (`GET/PUT /api/auth/profile`'s `language` field) — a separate concept
   from the site-wide UI language (`useLang()` / the header toggle). This
   section's own labels follow the UI language like every other card; the
   fa/en buttons below set the *account* preference and are left as the
   literal language names ("فارسی" / "English"), the same convention the
   header LanguageToggle itself uses ("فا" / "EN"). See useProfileData.ts
   for where the account preference is read/written. */
export default function AppearanceSection({ theme, setTheme, language, setLanguage }: AppearanceSectionProps) {
  const lang = useLang()
  const s = appearanceSectionStrings(lang)

  return (
    <div className="card profile-section-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="palette" size={16} className="text-accent" />
        <h2 className="card-title">
          {s.title}
        </h2>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {/* Theme toggle */}
        <div className="profile-toggle-row">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon name="moon" size={16} className="text-muted" />
            <div>
              <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
                {s.darkMode}
              </span>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                {s.darkModeHint}
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

        {/* Account language preference — independent of the header's UI
            language toggle; see the file comment above. */}
        <div className="profile-toggle-row">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon name="globe" size={16} className="text-muted" />
            <div>
              <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
                {s.languageLabel}
              </span>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                {s.languageHint}
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
