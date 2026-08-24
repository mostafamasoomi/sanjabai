import { Icon, type IconName } from '@/components/ui/Icon'

// ─── Empty State ────────────────────────────────────────────────────────────
export function EmptyStateIcon({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div className="wallet-empty-state">
      <div className="wallet-empty-icon-wrap">
        <Icon name={icon as IconName} size={28} className="text-accent" />
      </div>
      <p style={{ color: 'var(--text-secondary)', fontWeight: 600, marginBottom: 4, fontSize: 15 }}>{title}</p>
      <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>{desc}</p>
    </div>
  )
}
