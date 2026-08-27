'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { SectionHeader } from './shared'
import { purchasesSectionStrings } from './PurchasesSection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Purchases — a paginated, read-only table of completed credit-package
   purchases. New sub-tab of the products module (see productsTabs.ts),
   replacing the read-only "subscriptions" table that used to sit at the
   bottom of the retired PlansSection.tsx (whose pagination-fetch idiom this
   copies: `?page=&limit=` -> `{ items, total, page, limit }`).

   Server contract (pinned by the senior, backend endpoint built in
   parallel with this file):
     GET /api/admin/purchases?page=<int, default 1>&limit=<int, default 50>
     -> { purchases: [...], total: <int>, page: <int>, limit: <int> }

   The per-item shape was written provisionally, against a guess, while the
   endpoint was still being built in parallel — and then reconciled against
   the real `_PURCHASES_SQL` once it landed. One field of the guess did not
   survive: `gateway`. There is no such column, because Sanjabai has exactly
   one gateway; the backend declined to invent it, and the column it shows
   instead is `verified_at` — when the money actually cleared.

   The row shape stays confined to ONE place, the `PurchaseRow` type and the
   `renderRow` function below, so a future change to the endpoint is again a
   single-block edit. The fetch/pagination plumbing does not know or care
   what a row contains.
   ═══════════════════════════════════════════════════════════════════════════ */

/** Confirmed against `_PURCHASES_SQL` in backend/admin_packages.py.
 *
 *  `amount` is what Zarinpal actually charged; `total_credits` is what
 *  landed in the wallet, which is larger whenever the package carries a
 *  bonus_percent. Both are raw integer Toman and go through `f.price`
 *  untouched -- no component divides or multiplies by 10 (house law).
 *
 *  Every field but `id` is optional because the SQL LEFT JOINs
 *  credit_packages: a purchase whose package row was since deleted still
 *  appears, with the package columns null, rather than vanishing from the
 *  financial record. */
interface PurchaseRow {
  id: number | string
  user_id?: number | null
  email?: string | null
  phone?: string | null
  package_id?: string | null
  name_fa?: string | null
  name_en?: string | null
  amount?: number | null
  total_credits?: number | null
  status?: string | null
  created_at?: string | null
  verified_at?: string | null
}

interface PurchasesSectionProps {
  api: (path: string, opts?: RequestInit) => Promise<Response>
}

const PAGE_SIZE = 50

/** The one place that turns a `PurchaseRow` into table cells. Correct this
 *  function (and the `PurchaseRow` interface above) once the real backend
 *  keys are reported -- nothing else in this file needs to change. */
function renderRow(row: PurchaseRow, f: ReturnType<typeof fmt>, s: ReturnType<typeof purchasesSectionStrings>) {
  const user = row.email || row.phone || (row.user_id != null ? `#${f.num(row.user_id)}` : '—')
  const pkg = row.name_fa || row.name_en || row.package_id || '—'
  return (
    <tr key={String(row.id)}>
      <td className="p-3 text-xs" dir="ltr">{user}</td>
      <td className="p-3 text-xs">{pkg}</td>
      <td className="p-3 text-xs">{f.price(row.amount ?? null)}</td>
      <td className="p-3 text-xs">{f.price(row.total_credits ?? null)}</td>
      <td className="p-3 text-xs">{row.status || '—'}</td>
      <td className="p-3 text-xs">{f.date(row.verified_at ?? null)}</td>
      <td className="p-3 text-xs">{f.date(row.created_at ?? null)}</td>
    </tr>
  )
}

export default function PurchasesSection({ api }: PurchasesSectionProps) {
  const lang = useLang()
  const s = purchasesSectionStrings(lang)
  const f = fmt(lang)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rows, setRows] = useState<PurchaseRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)

  const load = useCallback(async (p: number) => {
    setLoading(true)
    setError(null)
    try {
      const res = await api(`/api/admin/purchases?page=${p}&limit=${PAGE_SIZE}`)
      const body = await res.json()
      setRows(Array.isArray(body.purchases) ? body.purchases : [])
      setTotal(typeof body.total === 'number' ? body.total : 0)
    } catch (err) {
      setError(err instanceof Error && err.message !== 'unauthorized' ? err.message : s.loadError)
    } finally {
      setLoading(false)
    }
  }, [api, s.loadError])

  useEffect(() => { load(page) }, [load, page])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="space-y-6">
      <SectionHeader title={s.title} subtitle={s.subtitle(f.num(total))} />

      <div className="admin-card">
        <div className="overflow-x-auto">
          <table className="admin-table w-full text-sm">
            <thead>
              <tr>
                <th className="p-3">{s.colUser}</th>
                <th className="p-3">{s.colPackage}</th>
                <th className="p-3">{s.colAmount}</th>
                <th className="p-3">{s.colCredits}</th>
                <th className="p-3">{s.colStatus}</th>
                <th className="p-3">{s.colVerifiedAt}</th>
                <th className="p-3">{s.colCreatedAt}</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} className="p-6 text-center text-sm text-muted">{s.loading}</td></tr>
              ) : error ? (
                <tr><td colSpan={7} className="p-6 text-center text-sm" style={{ color: 'var(--danger, #ef4444)' }}>
                  {error} — <button className="underline" onClick={() => load(page)}>{s.retry}</button>
                </td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={7} className="p-6 text-center text-sm text-muted">{s.noPurchases}</td></tr>
              ) : (
                rows.map((row) => renderRow(row, f, s))
              )}
            </tbody>
          </table>
        </div>
        {!loading && !error && total > 0 && (
          <div className="flex items-center justify-between mt-3 text-xs text-muted">
            <span>{s.page(f.num(page), f.num(totalPages), f.num(total))}</span>
            <div className="flex gap-2">
              <button className="btn btn-sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}>{s.prev}</button>
              <button className="btn btn-sm" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}>{s.next}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
