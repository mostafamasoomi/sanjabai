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

// ─── Numeric Input ───────────────────────────────────────────────────────────

/** Byte-identical control shared by PackagesSection.tsx and the rest of the
    admin forms -- it was copy-pasted per screen before, and moved here so a
    change to one no longer risks drifting from the other. (The second of
    the two original copies lived in PlansSection.tsx, deleted when the
    plan/subscription concept was retired.) */
export function NumInput({ value, onChange, width = 120, placeholder }: {
  value: string; onChange: (v: string) => void; width?: number; placeholder?: string
}) {
  return (
    <input
      className="input" type="number" min={0} value={value} placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)} style={{ maxWidth: width }}
    />
  )
}
