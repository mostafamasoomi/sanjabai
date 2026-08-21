'use client'

import { Icon } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════════════════
   Shared presentational helpers used by more than one extracted admin
   section. Moved out of AdminPanel.tsx verbatim — no behavior change.
   ═══════════════════════════════════════════════════════════════════════════ */

// ─── Stat Card ───────────────────────────────────────────────────────────────

export function StatCard({ icon, label, value, color }: { icon: React.ComponentProps<typeof Icon>['name']; label: string; value: string | number; color: string }) {
  return (
    <div className="admin-card" style={{ borderRight: `3px solid ${color}` }}>
      <div className="flex items-center gap-3 mb-2">
        <div className="p-2 rounded-lg" style={{ background: `${color}15` }}>
          <Icon name={icon} size={18} className="opacity-80" style={{ color }} />
        </div>
        <span className="text-xs text-muted">{label}</span>
      </div>
      <p className="text-2xl font-bold text-primary">{value}</p>
    </div>
  )
}

// ─── Section Header ──────────────────────────────────────────────────────────

export function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-xl font-bold text-primary">{title}</h1>
      {subtitle && <p className="text-sm mt-1 text-muted">{subtitle}</p>}
    </div>
  )
}

// ─── Form Field ──────────────────────────────────────────────────────────────

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium mb-1.5 text-secondary">{label}</label>
      {children}
    </div>
  )
}
