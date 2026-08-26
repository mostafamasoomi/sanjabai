import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { dirFor } from '@/lib/i18n'
import { searchHintBannerStrings } from './SearchHintBanner.strings'

type SearchHintBannerProps = {
  visible: boolean
  onResend: () => void
  onDismiss: () => void
}

// Offered when the user typed a search-intent message but the globe toggle
// was off -- never auto-enables search or auto-resends, only this click does.
export default function SearchHintBanner({ visible, onResend, onDismiss }: SearchHintBannerProps) {
  const lang = useLang()
  const s = searchHintBannerStrings(lang)
  if (!visible) return null
  return (
    <div
      dir={dirFor(lang)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '8px 14px',
        margin: '0 12px 8px',
        background: 'var(--bg-secondary, rgba(255,255,255,0.05))',
        border: '1px solid var(--border)',
        borderRadius: '10px',
        fontSize: '0.8125rem',
        color: 'var(--text-secondary)',
      }}
    >
      <Icon name="globe" size={14} />
      <span style={{ flex: 1 }}>
        {s.hint}
      </span>
      <button
        type="button"
        onClick={onResend}
        className="btn btn-ghost btn-sm"
        style={{ fontSize: '0.75rem', color: 'var(--accent)', whiteSpace: 'nowrap', fontWeight: 600 }}
      >
        {s.enableAndResend}
      </button>
      <button
        type="button"
        onClick={onDismiss}
        aria-label={s.close}
        style={{ display: 'inline-flex', background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: '2px' }}
      >
        <Icon name="close" size={12} />
      </button>
    </div>
  )
}
