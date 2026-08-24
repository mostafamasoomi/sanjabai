import { Icon } from '@/components/ui/Icon'
import { faNum, faDate } from '@/lib/format'

/* ═══════════════════════════════════════════════════════════════
   Subscription status card
   ═══════════════════════════════════════════════════════════════ */

export function SubscriptionCard({
  planName,
  subStatusColor,
  subStatusLabel,
  tokenQuota,
  tokensUsed,
  tokenPct,
  endsAt,
  onChangePlan,
}: {
  planName: string
  subStatusColor: string
  subStatusLabel: string
  tokenQuota: number
  tokensUsed: number
  tokenPct: number
  endsAt?: string
  onChangePlan: () => void
}) {
  return (
    <div className="card dash-span-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: 500 }}>وضعیت اشتراک</span>
        <div
          style={{
            width: '2rem',
            height: '2rem',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--accent-dim)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Icon name="dashboard" size={16} className="text-[var(--accent)]" />
        </div>
      </div>

      {/* Plan name */}
      <div style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--text-primary)' }}>
        {planName}
      </div>

      {/* Status badge */}
      <div className="flex items-center gap-2">
        <span
          style={{
            display: 'inline-block',
            width: '0.5rem',
            height: '0.5rem',
            borderRadius: '50%',
            background: subStatusColor,
          }}
        />
        <span style={{ fontSize: '0.75rem', fontWeight: 500, color: subStatusColor }}>
          {subStatusLabel}
        </span>
      </div>

      {/* Token usage progress bar */}
      {tokenQuota > 0 && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
            <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
              توکن مصرف شده
            </span>
            <span className="num" style={{ fontSize: 'var(--fs-2xs)', color: 'var(--text-secondary)' }}>
              {faNum(tokensUsed)} / {faNum(tokenQuota)}
            </span>
          </div>
          <div
            style={{
              width: '100%',
              height: '6px',
              borderRadius: '3px',
              background: 'var(--border)',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${tokenPct}%`,
                height: '100%',
                borderRadius: '3px',
                background: tokenPct > 90 ? 'var(--danger)' : tokenPct > 70 ? 'var(--warning)' : 'var(--accent)',
                transition: 'width 0.5s ease',
              }}
            />
          </div>
        </div>
      )}

      {/* Ends at */}
      {endsAt && (
        <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
          تاریخ پایان: {faDate(endsAt)}
        </div>
      )}

      {/* Change plan button */}
      <button
        className="btn btn-sm"
        onClick={onChangePlan}
        style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.375rem', marginTop: '0.25rem' }}
      >
        <Icon name="payment" size={14} />
        تغییر پلن
      </button>
    </div>
  )
}
