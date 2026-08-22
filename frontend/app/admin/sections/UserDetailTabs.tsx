'use client'

import { faNum, faPrice, faDate, faTime } from '@/lib/format'

/* ═══════════════════════════════════════════════════════════════════════════
   UserDetailTabs — presentational tables for the four data-heavy tabs of
   UserDetailDrawer.tsx (کیف پول/ledger, پرداخت‌ها, مصرف, گفتگوها). Split out
   of the drawer itself purely to stay under the repo's 500-line-per-file
   cap; these components own no state and no fetching — UserDetailDrawer.tsx
   fetches and owns a `TabState<T>` per tab and hands it down here.

   Backend response shapes (backend/admin.py, backend/admin_user_ops.py):
     GET /admin/users/{uid}/ledger      -> { items: LedgerRow[], total, page, limit }
     GET /admin/users/{uid}/payments    -> { payments: PaymentRow[], subscriptions: SubscriptionRow[] }
     GET /admin/users/{uid}/usage       -> { by_model: UsageByModelRow[], daily: UsageDailyRow[] }
     GET /admin/users/{uid}/conversations -> { items: ConversationRow[], total, page, limit }

   NOTE (worth flagging to the backend owner): admin_user_ledger's SELECT
   only returns id/amount/balance_after/reason/created_at — no `txn_type`,
   even though every ledger write path (services/billing.py,
   admin_user_ops.py's credit/debit) sets one. An admin reading this tab
   cannot tell an `admin_credit` apart from a `chat_settle` apart from a
   `referral_bonus` except by the free-text `reason` string. Money here is
   already integer toman — never divide/multiply by 10, render only via
   faPrice/faNum.
   ═══════════════════════════════════════════════════════════════════════════ */

export type TabStatus = 'idle' | 'loading' | 'error' | 'ready'

export interface TabState<T> {
  status: TabStatus
  data: T | null
  error: string
}

export const IDLE_TAB_STATE: TabState<never> = { status: 'idle', data: null, error: '' }

export interface LedgerRow {
  id: number
  amount: number
  balance_after: number
  reason: string
  created_at: string
}
export interface LedgerPayload { items: LedgerRow[]; total: number }

export interface PaymentRow {
  id: number
  amount: number
  authority: string | null
  ref_id: string | null
  status: string
  payment_type: string | null
  created_at: string
  verified_at: string | null
}
export interface SubscriptionRow {
  id?: number
  plan?: string
  status?: string
  starts_at?: string
  ends_at?: string | null
  price_paid?: number
}
export interface PaymentsPayload { payments: PaymentRow[]; subscriptions: SubscriptionRow[] }

export interface UsageByModelRow {
  model: string
  calls: number
  input_tokens: number
  output_tokens: number
  total_cost: number
  last_used: string | null
}
export interface UsageDailyRow { day: string; tokens: number; cost: number; calls: number }
export interface UsagePayload { by_model: UsageByModelRow[]; daily: UsageDailyRow[] }

export interface ConversationRow {
  id: number
  title: string | null
  model: string | null
  created_at: string
  updated_at: string
  msg_count: number
}
export interface ConversationsPayload { items: ConversationRow[]; total: number }

// ─── Shared loading / error / empty shell ───────────────────────────────────

function StateShell<T>({
  state, isEmpty, children,
}: { state: TabState<T>; isEmpty: (d: T) => boolean; children: (d: T) => React.ReactNode }) {
  if (state.status === 'idle' || state.status === 'loading') {
    return <div className="skeleton h-28 w-full rounded" />
  }
  if (state.status === 'error') {
    return (
      <p className="p-4 text-sm text-danger">
        {state.error || 'خطا در دریافت اطلاعات — لطفاً دوباره تلاش کنید'}
      </p>
    )
  }
  if (!state.data || isEmpty(state.data)) {
    return <p className="p-6 text-center text-sm text-muted">چیزی ثبت نشده</p>
  }
  return <>{children(state.data)}</>
}

// ─── کیف پول (ledger rows only — the wallet-adjust form lives beside this) ──

export function LedgerTab({ state }: { state: TabState<LedgerPayload> }) {
  return (
    <StateShell state={state} isEmpty={(d) => d.items.length === 0}>
      {(d) => (
        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="text-right p-2">شناسه</th>
                <th className="text-right p-2">مبلغ</th>
                <th className="text-right p-2">مانده پس از تراکنش</th>
                <th className="text-right p-2">شرح</th>
                <th className="text-right p-2">تاریخ</th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((l) => (
                <tr key={l.id}>
                  <td className="p-2 text-xs font-mono">{faNum(l.id)}</td>
                  <td className={`p-2 text-xs font-bold ${l.amount >= 0 ? 'text-positive' : 'text-danger'}`}>
                    {faPrice(l.amount, { signed: true })}
                  </td>
                  <td className="p-2 text-xs">{faPrice(l.balance_after)}</td>
                  <td className="p-2 text-xs text-secondary">{l.reason || '—'}</td>
                  <td className="p-2 text-xs">{faDate(l.created_at)} {faTime(l.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs mt-2 text-muted">{faNum(d.total)} تراکنش</p>
        </div>
      )}
    </StateShell>
  )
}

// ─── پرداخت‌ها ────────────────────────────────────────────────────────────

const PAYMENT_STATUS_FA: Record<string, string> = {
  verified: 'تایید شده', pending: 'در انتظار', failed: 'ناموفق',
}

export function PaymentsTab({ state }: { state: TabState<PaymentsPayload> }) {
  return (
    <StateShell state={state} isEmpty={(d) => d.payments.length === 0 && d.subscriptions.length === 0}>
      {(d) => (
        <div className="space-y-4">
          {d.payments.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="admin-table w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-right p-2">شناسه</th>
                    <th className="text-right p-2">مبلغ</th>
                    <th className="text-right p-2">وضعیت</th>
                    <th className="text-right p-2">نوع</th>
                    <th className="text-right p-2">کد مرجع</th>
                    <th className="text-right p-2">تاریخ</th>
                  </tr>
                </thead>
                <tbody>
                  {d.payments.map((p) => (
                    <tr key={p.id}>
                      <td className="p-2 text-xs font-mono">{faNum(p.id)}</td>
                      <td className="p-2 text-xs font-bold">{faPrice(p.amount)}</td>
                      <td className="p-2">
                        <span className={`badge ${p.status === 'verified' ? 'badge-positive' : p.status === 'pending' ? 'badge-accent' : 'badge-danger'}`}>
                          {PAYMENT_STATUS_FA[p.status] || p.status}
                        </span>
                      </td>
                      <td className="p-2 text-xs">{p.payment_type || '—'}</td>
                      <td className="p-2 text-xs font-mono">{p.ref_id || '—'}</td>
                      <td className="p-2 text-xs">{faDate(p.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted">هیچ پرداختی ثبت نشده</p>
          )}
          {d.subscriptions.length > 0 && (
            <>
              <h3 className="text-sm font-bold text-primary">اشتراک‌ها</h3>
              <table className="admin-table w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-right p-2">پلن</th>
                    <th className="text-right p-2">وضعیت</th>
                    <th className="text-right p-2">شروع</th>
                    <th className="text-right p-2">پایان</th>
                    <th className="text-right p-2">مبلغ</th>
                  </tr>
                </thead>
                <tbody>
                  {d.subscriptions.map((s, i) => (
                    <tr key={s.id ?? i}>
                      <td className="p-2 text-xs font-medium">{s.plan || '—'}</td>
                      <td className="p-2">
                        <span className={`badge ${s.status === 'active' ? 'badge-positive' : 'badge-accent'}`}>
                          {s.status === 'active' ? 'فعال' : s.status || '—'}
                        </span>
                      </td>
                      <td className="p-2 text-xs">{faDate(s.starts_at)}</td>
                      <td className="p-2 text-xs">{s.ends_at ? faDate(s.ends_at) : '—'}</td>
                      <td className="p-2 text-xs">{faPrice(s.price_paid)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}
    </StateShell>
  )
}

// ─── مصرف ────────────────────────────────────────────────────────────────

/** Hand-rolled SVG bars — recharts is banned in this project (breaks the
    build; see AdminCharts.tsx). Oldest day on the right, newest on the
    left, matching RTL reading order. */
function DailyUsageChart({ daily }: { daily: UsageDailyRow[] }) {
  const rows = [...daily].reverse()
  const max = Math.max(1, ...rows.map((r) => Number(r.tokens) || 0))
  const barW = 18
  const gap = 6
  const chartH = 90
  const width = rows.length * (barW + gap) + gap

  return (
    <div className="overflow-x-auto">
      <svg
        width={width}
        height={chartH + 20}
        viewBox={`0 0 ${width} ${chartH + 20}`}
        style={{ minWidth: '100%' }}
        role="img"
        aria-label="مصرف توکن روزانه"
      >
        {rows.map((r, i) => {
          const h = Math.max(2, (Number(r.tokens) / max) * chartH)
          // RTL: first (oldest) bar drawn at the right edge.
          const x = width - gap - (i + 1) * (barW + gap) + gap
          return (
            <g key={r.day}>
              <rect
                x={x} y={chartH - h + 10} width={barW} height={h}
                rx={3} fill="var(--accent)" opacity={0.85}
              >
                <title>{`${faDate(r.day)}: ${faNum(r.tokens)} توکن`}</title>
              </rect>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

export function UsageTab({ state }: { state: TabState<UsagePayload> }) {
  return (
    <StateShell state={state} isEmpty={(d) => d.by_model.length === 0}>
      {(d) => (
        <div className="space-y-5">
          <div>
            <h3 className="text-sm font-bold text-primary mb-2">مصرف بر اساس مدل</h3>
            <table className="admin-table w-full text-sm">
              <thead>
                <tr>
                  <th className="text-right p-2">مدل</th>
                  <th className="text-right p-2">درخواست</th>
                  <th className="text-right p-2">ورودی</th>
                  <th className="text-right p-2">خروجی</th>
                  <th className="text-right p-2">هزینه</th>
                  <th className="text-right p-2">آخرین استفاده</th>
                </tr>
              </thead>
              <tbody>
                {d.by_model.map((m, i) => (
                  <tr key={`${m.model}-${i}`}>
                    <td className="p-2 text-xs font-medium">{m.model}</td>
                    <td className="p-2 text-xs">{faNum(m.calls)}</td>
                    <td className="p-2 text-xs">{faNum(m.input_tokens)}</td>
                    <td className="p-2 text-xs">{faNum(m.output_tokens)}</td>
                    <td className="p-2 text-xs">{faPrice(m.total_cost)}</td>
                    <td className="p-2 text-xs">{m.last_used ? faDate(m.last_used) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {d.daily.length > 0 && (
            <div>
              <h3 className="text-sm font-bold text-primary mb-2">مصرف توکن ۳۰ روز اخیر</h3>
              <DailyUsageChart daily={d.daily} />
            </div>
          )}
        </div>
      )}
    </StateShell>
  )
}

// ─── گفتگوها ──────────────────────────────────────────────────────────────

export function ConversationsTab({ state }: { state: TabState<ConversationsPayload> }) {
  return (
    <StateShell state={state} isEmpty={(d) => d.items.length === 0}>
      {(d) => (
        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="text-right p-2">شناسه</th>
                <th className="text-right p-2">عنوان</th>
                <th className="text-right p-2">مدل</th>
                <th className="text-right p-2">پیام‌ها</th>
                <th className="text-right p-2">آخرین بروزرسانی</th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((c) => (
                <tr key={c.id}>
                  <td className="p-2 text-xs font-mono">{faNum(c.id)}</td>
                  <td className="p-2 text-xs">{c.title || '—'}</td>
                  <td className="p-2 text-xs"><span className="badge badge-accent">{c.model || '—'}</span></td>
                  <td className="p-2 text-xs">{faNum(c.msg_count)}</td>
                  <td className="p-2 text-xs">{faDate(c.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs mt-2 text-muted">{faNum(d.total)} گفتگو</p>
        </div>
      )}
    </StateShell>
  )
}
