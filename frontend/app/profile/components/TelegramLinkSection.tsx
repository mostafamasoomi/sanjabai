'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { telegramLinkSectionStrings } from './TelegramLinkSection.strings'

type TelegramLinkSectionProps = {
  telegramId: string
  setTelegramId: (v: string) => void
  linkingTelegram: boolean
  handleLinkTelegram: () => void
}

export default function TelegramLinkSection({
  telegramId, setTelegramId, linkingTelegram, handleLinkTelegram,
}: TelegramLinkSectionProps) {
  const lang = useLang()
  const s = telegramLinkSectionStrings(lang)

  return (
    <div className="card profile-section-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Icon name="send" size={16} className="text-accent" />
        <h2 className="card-title">
          {s.title}
        </h2>
      </div>
      <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
        {s.intro}
      </p>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          type="number"
          value={telegramId}
          onChange={(e) => setTelegramId(e.target.value)}
          placeholder={s.idPlaceholder}
          className="input flex-1"
        />
        <button
          onClick={handleLinkTelegram}
          disabled={linkingTelegram || !telegramId}
          className="btn btn-secondary"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
        >
          {linkingTelegram ? (
            <span className="apikeys-spinner" />
          ) : (
            <Icon name="link" size={14} />
          )}
          {s.link}
        </button>
      </div>
      <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
        <Icon name="info" size={12} />
        {s.hint}
      </p>
    </div>
  )
}
