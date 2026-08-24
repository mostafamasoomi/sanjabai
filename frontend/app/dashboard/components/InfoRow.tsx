import { Icon, type IconName } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════
   Info Row (for account card)
   ═══════════════════════════════════════════════════════════════ */

export function InfoRow({ icon, label, value }: { icon: IconName; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 min-w-0">
        <span className="shrink-0 text-[var(--text-muted)]">
          <Icon name={icon} size={14} />
        </span>
        <span className="text-xs text-[var(--text-secondary)]">{label}</span>
      </div>
      <span className="text-[13px] font-medium text-[var(--text-primary)] overflow-hidden text-ellipsis whitespace-nowrap text-end">
        {value}
      </span>
    </div>
  )
}
