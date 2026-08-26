'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { profileErrorBannerStrings } from './ProfileErrorBanner.strings'

type ProfileErrorBannerProps = {
  onRetry: () => void
}

// Profile load error — the fetch used to fail silently, leaving the
// form blank with no explanation.
export default function ProfileErrorBanner({ onRetry }: ProfileErrorBannerProps) {
  const lang = useLang()
  const s = profileErrorBannerStrings(lang)
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
        {s.loadFailed}
      </span>
      <button
        onClick={onRetry}
        className="btn btn-sm btn-secondary"
        style={{ flexShrink: 0 }}
      >
        {s.retry}
      </button>
    </div>
  )
}
