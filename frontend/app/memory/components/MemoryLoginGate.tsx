import { EmptyState } from '@/components/ui'

/* ═══════════════════════════════════════════════════════════════
   Login gate: auth-loading skeleton, or the logged-out empty state.
   Split out of page.tsx verbatim -- no behaviour change.

   Unlike /skills and /tasks, this page previously had no gate at all
   and read the token straight out of localStorage in four places
   instead of going through useAuth — a logged-out visitor saw an
   empty "no memories" state instead of a login prompt, and every
   mutating action failed silently against `Authorization: Bearer
   null`.
   ═══════════════════════════════════════════════════════════════ */

export function MemoryLoginGate({ authLoading }: { authLoading: boolean }) {
  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '0 16px' }}>
      {authLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[1, 2, 3].map((i) => (
            <div key={i} className="card">
              <div className="skeleton" style={{ height: 14, width: '70%', marginBottom: 8 }} />
              <div className="skeleton" style={{ height: 10, width: '40%' }} />
            </div>
          ))}
        </div>
      ) : (
        <EmptyState icon="lock" title="برای مشاهده حافظه وارد شوید" description="ابتدا باید وارد حساب خود شوید." />
      )}
    </div>
  )
}
