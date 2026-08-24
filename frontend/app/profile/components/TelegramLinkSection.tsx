import { Icon } from '@/components/ui/Icon'

type TelegramLinkSectionProps = {
  isFa: boolean
  telegramId: string
  setTelegramId: (v: string) => void
  linkingTelegram: boolean
  handleLinkTelegram: () => void
}

export default function TelegramLinkSection({
  isFa, telegramId, setTelegramId, linkingTelegram, handleLinkTelegram,
}: TelegramLinkSectionProps) {
  return (
    <div className="card profile-section-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Icon name="send" size={16} className="text-accent" />
        <h2 className="card-title">
          {isFa ? 'اتصال تلگرام' : 'Link Telegram'}
        </h2>
      </div>
      <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
        {isFa
          ? 'با اتصال حساب تلگرام می‌توانید از طریق ربات Sanjabai چت کنید و موجودی خود را ببینید.'
          : 'Link your Telegram account to chat via the Sanjabai bot and view your balance.'}
      </p>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          type="number"
          value={telegramId}
          onChange={(e) => setTelegramId(e.target.value)}
          placeholder={isFa ? 'شناسه عددی تلگرام (Telegram ID)' : 'Telegram numeric ID'}
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
          {isFa ? 'اتصال' : 'Link'}
        </button>
      </div>
      <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
        <Icon name="info" size={12} />
        {isFa
          ? 'برای دریافت شناسه تلگرام، به ربات @userinfobot پیام دهید.'
          : 'To get your Telegram ID, message @userinfobot.'}
      </p>
    </div>
  )
}
