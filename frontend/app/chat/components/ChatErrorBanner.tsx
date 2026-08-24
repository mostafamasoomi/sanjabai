import { Icon } from '@/components/ui/Icon'

type ChatErrorBannerProps = {
  error: string
}

export default function ChatErrorBanner({ error }: ChatErrorBannerProps) {
  if (!error) return null
  if (error !== 'INSUFFICIENT_BALANCE') {
    return (
      <div className="chat-error">
        <Icon name="close" size={14} />
        {error}
      </div>
    )
  }
  return (
    <div className="chat-error chat-error-balance" style={{
      background: 'linear-gradient(135deg, rgba(243,156,18,0.12), rgba(231,76,60,0.08))',
      border: '1px solid rgba(243,156,18,0.3)',
      borderRadius: '16px',
      padding: '20px 24px',
      display: 'flex',
      flexDirection: 'column',
      gap: '12px',
      alignItems: 'center',
      textAlign: 'center',
      margin: '12px 0',
    }}>
      <div style={{ fontSize: '2rem' }}>💳</div>
      <div style={{ fontWeight: 700, fontSize: '1.05rem', color: 'var(--text-primary)' }}>
        اعتبار شما تمام شده!
      </div>
      <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
        برای ادامه استفاده از مدل‌های هوش مصنوعی، نیاز به شارژ حساب دارید.
        <br />
        با شارژ حساب میتونید بدون محدودیت از تمام مدل‌ها استفاده کنید.
      </div>
      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', justifyContent: 'center' }}>
        <a href="/pricing" className="btn btn-primary" style={{ textDecoration: 'none', padding: '10px 24px', borderRadius: '10px', fontWeight: 600, fontSize: '0.9rem' }}>
          🚀 مشاهده پلنها و شارژ حساب
        </a>
        <a href="/wallet" className="btn btn-ghost" style={{ textDecoration: 'none', padding: '10px 20px', borderRadius: '10px', fontWeight: 500, fontSize: '0.9rem' }}>
          💰 کیف پول
        </a>
      </div>
    </div>
  )
}
