import { Icon } from '@/components/ui/Icon'

type ProfileErrorBannerProps = {
  isFa: boolean
  onRetry: () => void
}

// Profile load error — the fetch used to fail silently, leaving the
// form blank with no explanation.
export default function ProfileErrorBanner({ isFa, onRetry }: ProfileErrorBannerProps) {
  return (
    <div
      role="alert"
      className="card"
      style={{
        display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16,
        border: '1px solid var(--danger)',
        background: 'color-mix(in srgb, var(--danger) 12%, transparent)',
      }}
    >
      <span style={{ color: 'var(--danger)', flexShrink: 0 }}>
        <Icon name="warning" size={18} />
      </span>
      <span style={{ flex: 1, fontSize: 13, color: 'var(--text-primary)' }}>
        {isFa ? 'خطا در بارگذاری اطلاعات پروفایل. لطفاً صفحه را تازه‌سازی کنید.' : 'Failed to load your profile. Please refresh the page.'}
      </span>
      <button
        onClick={onRetry}
        className="btn btn-sm btn-secondary"
        style={{ flexShrink: 0 }}
      >
        {isFa ? 'تلاش مجدد' : 'Retry'}
      </button>
    </div>
  )
}
