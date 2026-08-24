import { Icon } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════
   Static "auto memory" info card. Split out of page.tsx verbatim --
   no behaviour change.
   ═══════════════════════════════════════════════════════════════ */

export function MemoryInfoCard() {
  return (
    <div
      className="card"
      style={{
        marginBottom: 20,
        background: 'var(--accent-dim)',
        borderColor: 'var(--accent)',
        borderWidth: 1,
      }}
    >
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
        <Icon name="info" size={16} style={{ color: 'var(--accent)', marginTop: 2, flexShrink: 0 }} />
        <div>
          <h4 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
            حافظه خودکار
          </h4>
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            سیستم به‌صورت خودکار اطلاعات مهم شما را از مکالمات استخراج و ذخیره می‌کند.
            این اطلاعات در چت‌های آینده برای ارائه پاسخ‌های شخصی‌تر استفاده می‌شود.
          </p>
        </div>
      </div>
    </div>
  )
}
