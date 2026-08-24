import { Icon, type IconName } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════
   Quick Action Button
   ═══════════════════════════════════════════════════════════════ */

export function QuickAction({
  icon,
  label,
  description,
  onClick,
}: {
  icon: IconName
  label: string
  description: string
  onClick: () => void
}) {
  return (
    <button
      className="card-interactive"
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        padding: '1rem',
        textAlign: 'right',
        width: '100%',
        cursor: 'pointer',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        background: 'var(--bg-surface)',
        transition: 'all var(--motion-fast) ease',
      }}
    >
      <div
        style={{
          width: '2.5rem',
          height: '2.5rem',
          borderRadius: 'var(--radius-sm)',
          background: 'var(--accent-dim)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <Icon name={icon} size={18} className="text-[var(--accent)]" />
      </div>
      <div className="flex-1 min-w-0">
        <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>{label}</div>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.125rem' }}>{description}</div>
      </div>
      <span className="shrink-0 text-[var(--text-muted)]">
        <Icon name="arrowLeft" size={16} />
      </span>
    </button>
  )
}
