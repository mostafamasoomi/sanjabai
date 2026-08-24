import { Icon } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════
   Page header. Split out of page.tsx verbatim -- no behaviour change.
   ═══════════════════════════════════════════════════════════════ */

export function MemoryHeader() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
      <div
        style={{
          width: 40,
          height: 40,
          borderRadius: 'var(--radius-lg)',
          background: 'var(--accent-dim)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Icon name="sparkles" size={20} className="text-accent" />
      </div>
      <div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.2 }}>
          حافظه هوشمند
        </h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 2 }}>
          اطلاعات و ترجیحات شما برای چت‌های بهتر
        </p>
      </div>
    </div>
  )
}
