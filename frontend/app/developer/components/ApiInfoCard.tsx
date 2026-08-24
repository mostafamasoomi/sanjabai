import { Icon } from '@/components/ui/Icon'
import { RATE_LIMITS } from '../constants'

export function ApiInfoCard() {
  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="external" size={16} className="text-accent" />
        <h2 className="card-title">اطلاعات API</h2>
      </div>

      <div style={{
        padding: '14px 18px', borderRadius: 10,
        background: 'linear-gradient(135deg, rgba(139,92,246,0.1), rgba(109,40,217,0.05))',
        border: '1px solid rgba(139,92,246,0.2)',
        marginBottom: 16,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Icon name="info" size={14} className="text-accent" />
          <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>Endpoint</span>
        </div>
        <code style={{
          display: 'block', direction: 'ltr', fontFamily: 'var(--font-mono)',
          fontSize: 15, fontWeight: 700, color: 'var(--accent)',
        }}>
          https://sanjabai.com/v1
        </code>
        <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '6px 0 0' }}>
          API سازگار با فرمت OpenAI — بدون تغییر در کد اصلی ادغام دهید.
        </p>
      </div>

      {/* Rate Limits */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
        <Icon name="chart" size={14} className="text-muted" />
        <h3 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>محدودیت‌های نرخی بر اساس پلن</h3>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              <th style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--text-muted)', fontWeight: 600 }}>پلن</th>
              <th style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--text-muted)', fontWeight: 600 }}>محدودیت درخواست</th>
            </tr>
          </thead>
          <tbody>
            {RATE_LIMITS.map((r) => (
              <tr key={r.plan} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '8px 12px', color: 'var(--text-primary)', fontWeight: 600 }}>{r.plan}</td>
                <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>{r.requests}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
