'use client'

import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/adminI18n'
import { userDetailTabsStrings } from './UserDetailTabs.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   UserDetailTabs — presentational tables for the four data-heavy tabs of
   UserDetailDrawer.tsx (wallet/ledger, payments, usage, conversations). Split
   out of the drawer itself purely to stay under the repo's 500-line-per-file
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
   f.price/f.num (see lib/adminI18n.ts).
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
  const lang = useLang()
  const s = userDetailTabsStrings(lang)

  if (state.status === 'idle' || state.status === 'loading') {
    return <div className="skeleton h-28 w-full rounded" />
  }
  if (state.status === 'error') {
    return (
      <p className="p-4 text-sm text-danger">
        {state.error || s.loadError}
      </p>
    )
  }
  if (!state.data || isEmpty(state.data)) {
    return <p className="p-6 text-center text-sm text-muted">{s.empty}</p>
  }
  return <>{children(state.data)}</>
}

// ─── wallet ledger (rows only — the wallet-adjust form lives beside this) ───

export function LedgerTab({ state }: { state: TabState<LedgerPayload> }) {
  const lang = useLang()
  const s = userDetailTabsStrings(lang)
  const f = fmt(lang)

  return (
    <StateShell state={state} isEmpty={(d) => d.items.length === 0}>
      {(d) => (
        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="text-right p-2">{s.colId}</th>
                <th className="text-right p-2">{s.colAmount}</th>
                <th className="text-right p-2">{s.colBalanceAfter}</th>
                <th className="text-right p-2">{s.colReason}</th>
                <th className="text-right p-2">{s.colDate}</th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((l) => (
                <tr key={l.id}>
                  <td className="p-2 text-xs font-mono">{f.num(l.id)}</td>
                  <td className={`p-2 text-xs font-bold ${l.amount >= 0 ? 'text-positive' : 'text-danger'}`}>
                    {f.price(l.amount, { signed: true })}
                  </td>
                  <td className="p-2 text-xs">{f.price(l.balance_after)}</td>
                  <td className="p-2 text-xs text-secondary">{l.reason || '—'}</td>
                  <td className="p-2 text-xs">{f.date(l.created_at)} {f.time(l.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs mt-2 text-muted">{s.txCount(f.num(d.total))}</p>
        </div>
      )}
    </StateShell>
  )
}

// ─── payments ────────────────────────────────────────────────────────────

export function PaymentsTab({ state }: { state: TabState<PaymentsPayload> }) {
  const lang = useLang()
  const s = userDetailTabsStrings(lang)
  const f = fmt(lang)

  return (
    <StateShell state={state} isEmpty={(d) => d.payments.length === 0 && d.subscriptions.length === 0}>
      {(d) => (
        <div className="space-y-4">
          {d.payments.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="admin-table w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-right p-2">{s.colId}</th>
                    <th className="text-right p-2">{s.colAmount}</th>
                    <th className="text-right p-2">{s.colStatus}</th>
                    <th className="text-right p-2">{s.colType}</th>
                    <th className="text-right p-2">{s.colRefCode}</th>
                    <th className="text-right p-2">{s.colDate}</th>
                  </tr>
                </thead>
                <tbody>
                  {d.payments.map((p) => (
                    <tr key={p.id}>
                      <td className="p-2 text-xs font-mono">{f.num(p.id)}</td>
                      <td className="p-2 text-xs font-bold">{f.price(p.amount)}</td>
                      <td className="p-2">
                        <span className={`badge ${p.status === 'verified' ? 'badge-positive' : p.status === 'pending' ? 'badge-accent' : 'badge-danger'}`}>
                          {s.paymentStatus[p.status] || p.status}
                        </span>
                      </td>
                      <td className="p-2 text-xs">{p.payment_type || '—'}</td>
                      <td className="p-2 text-xs font-mono">{p.ref_id || '—'}</td>
                      <td className="p-2 text-xs">{f.date(p.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted">{s.noPayments}</p>
          )}
          {d.subscriptions.length > 0 && (
            <>
              <h3 className="text-sm font-bold text-primary">{s.subscriptionsTitle}</h3>
              <table className="admin-table w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-right p-2">{s.colPlan}</th>
                    <th className="text-right p-2">{s.colStatus}</th>
                    <th className="text-right p-2">{s.colStart}</th>
                    <th className="text-right p-2">{s.colEnd}</th>
                    <th className="text-right p-2">{s.colAmount}</th>
                  </tr>
                </thead>
                <tbody>
                  {d.subscriptions.map((sub, i) => (
                    <tr key={sub.id ?? i}>
                      <td className="p-2 text-xs font-medium">{sub.plan || '—'}</td>
                      <td className="p-2">
                        <span className={`badge ${sub.status === 'active' ? 'badge-positive' : 'badge-accent'}`}>
                          {sub.status === 'active' ? s.subActive : sub.status || '—'}
                        </span>
                      </td>
                      <td className="p-2 text-xs">{f.date(sub.starts_at)}</td>
                      <td className="p-2 text-xs">{sub.ends_at ? f.date(sub.ends_at) : '—'}</td>
                      <td className="p-2 text-xs">{f.price(sub.price_paid)}</td>
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

// ─── usage ───────────────────────────────────────────────────────────────

/** Hand-rolled SVG bars — recharts is banned in this project (breaks the
    build; see AdminCharts.tsx). Oldest day at the trailing edge, newest at
    the leading edge, matching the panel's reading order. */
function DailyUsageChart({ daily }: { daily: UsageDailyRow[] }) {
  const lang = useLang()
  const s = userDetailTabsStrings(lang)
  const f = fmt(lang)

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
        aria-label={s.chartAriaLabel}
      >
        {rows.map((r, i) => {
          const h = Math.max(2, (Number(r.tokens) / max) * chartH)
          // First (oldest) bar drawn at the trailing edge for the language's
          // reading order (right edge in RTL, left edge in LTR).
          const x = width - gap - (i + 1) * (barW + gap) + gap
          return (
            <g key={r.day}>
              <rect
                x={x} y={chartH - h + 10} width={barW} height={h}
                rx={3} fill="var(--accent)" opacity={0.85}
              >
                <title>{s.chartTooltip(f.date(r.day), f.num(r.tokens))}</title>
              </rect>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

export function UsageTab({ state }: { state: TabState<UsagePayload> }) {
  const lang = useLang()
  const s = userDetailTabsStrings(lang)
  const f = fmt(lang)

  return (
    <StateShell state={state} isEmpty={(d) => d.by_model.length === 0}>
      {(d) => (
        <div className="space-y-5">
          <div>
            <h3 className="text-sm font-bold text-primary mb-2">{s.usageByModelTitle}</h3>
            <table className="admin-table w-full text-sm">
              <thead>
                <tr>
                  <th className="text-right p-2">{s.colModel}</th>
                  <th className="text-right p-2">{s.colCalls}</th>
                  <th className="text-right p-2">{s.colInput}</th>
                  <th className="text-right p-2">{s.colOutput}</th>
                  <th className="text-right p-2">{s.colCost}</th>
                  <th className="text-right p-2">{s.colLastUsed}</th>
                </tr>
              </thead>
              <tbody>
                {d.by_model.map((m, i) => (
                  <tr key={`${m.model}-${i}`}>
                    <td className="p-2 text-xs font-medium">{m.model}</td>
                    <td className="p-2 text-xs">{f.num(m.calls)}</td>
                    <td className="p-2 text-xs">{f.num(m.input_tokens)}</td>
                    <td className="p-2 text-xs">{f.num(m.output_tokens)}</td>
                    <td className="p-2 text-xs">{f.price(m.total_cost)}</td>
                    <td className="p-2 text-xs">{m.last_used ? f.date(m.last_used) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {d.daily.length > 0 && (
            <div>
              <h3 className="text-sm font-bold text-primary mb-2">{s.dailyUsageTitle}</h3>
              <DailyUsageChart daily={d.daily} />
            </div>
          )}
        </div>
      )}
    </StateShell>
  )
}

// ─── conversations ──────────────────────────────────────────────────────

export function ConversationsTab({ state }: { state: TabState<ConversationsPayload> }) {
  const lang = useLang()
  const s = userDetailTabsStrings(lang)
  const f = fmt(lang)

  return (
    <StateShell state={state} isEmpty={(d) => d.items.length === 0}>
      {(d) => (
        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="text-right p-2">{s.colId}</th>
                <th className="text-right p-2">{s.colTitle}</th>
                <th className="text-right p-2">{s.colModel}</th>
                <th className="text-right p-2">{s.colMessages}</th>
                <th className="text-right p-2">{s.colLastUpdated}</th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((c) => (
                <tr key={c.id}>
                  <td className="p-2 text-xs font-mono">{f.num(c.id)}</td>
                  <td className="p-2 text-xs">{c.title || '—'}</td>
                  <td className="p-2 text-xs"><span className="badge badge-accent">{c.model || '—'}</span></td>
                  <td className="p-2 text-xs">{f.num(c.msg_count)}</td>
                  <td className="p-2 text-xs">{f.date(c.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs mt-2 text-muted">{s.convCount(f.num(d.total))}</p>
        </div>
      )}
    </StateShell>
  )
}
