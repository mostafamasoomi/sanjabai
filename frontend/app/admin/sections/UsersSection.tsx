'use client'

import { useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { SectionHeader, Field } from './shared'
import { ErrorCard, RefreshButton, CardSkeleton } from './LoadState'
import UserDetailDrawer from './UserDetailDrawer'
import { api, errMessage } from '../api'
import { useAdminResource } from '../useAdminResource'
import type { UserRow } from '../types'
import { usersSectionStrings } from './UsersSection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Users — self-contained: owns the list, the search box, the edit modal and
   the ban call. Previously all of that lived in AdminPanel.tsx and arrived
   through fourteen props.

   Backend contract (backend/admin_users.py, read directly):
     GET  /admin/users?page&limit  -> { users, total, page, limit }; `limit`
                                      is capped at 200 server-side, so the
                                      header states how many of `total` are
                                      actually on screen rather than implying
                                      the table is the whole population.
     POST /admin/users/{uid}/ban   -> a TOGGLE, and the only ban route there
                                      is. There is no DELETE verb on it.
     PUT  /admin/users/{uid}       <- {email?, phone?, daily_limit?} only.
                                      Sending `balance` makes the endpoint
                                      refuse the whole request with 400 and
                                      apply none of the other fields.
   ═══════════════════════════════════════════════════════════════════════════ */

const PAGE_LIMIT = 200

interface UsersPayload {
  rows: UserRow[]
  total: number
}

export default function UsersSection() {
  const lang = useLang()
  const s = usersSectionStrings(lang)
  const f = fmt(lang)

  const { data, error, loading, reload, setData } = useAdminResource<UsersPayload>(
    `/api/admin/users?limit=${PAGE_LIMIT}`,
    (raw) => ({
      rows: (Array.isArray(raw) ? raw : raw?.users) || [],
      total: typeof raw?.total === 'number' ? raw.total : (raw?.users || raw || []).length,
    }),
    s.fetchError,
  )

  const [userSearch, setUserSearch] = useState('')
  const [editingUser, setEditingUser] = useState<UserRow | null>(null)
  const [saving, setSaving] = useState(false)
  const [drawerUid, setDrawerUid] = useState<number | null>(null)

  const users = data?.rows || []
  const total = data?.total || 0

  // POST, not DELETE: the backend exposes a single toggle route and the old
  // DELETE call 405'd every time, so "unban" never did anything.
  const toggleBan = async (uid: number) => {
    try {
      const res = await api(`/api/admin/users/${uid}/ban`, { method: 'POST' })
      const body = await res.json()
      const banned = body?.banned !== false
      setData((prev) => (prev ? { ...prev, rows: prev.rows.map((u) => (u.id === uid ? { ...u, banned } : u)) } : prev))
      toast(banned ? s.banSuccess : s.unbanSuccess, 'success')
    } catch (err) {
      toast(errMessage(err, s.banError), 'error')
    }
  }

  const saveUserEdit = async () => {
    if (!editingUser) return
    setSaving(true)
    try {
      // Only the two fields this modal edits. The whole UserRow used to go
      // out here, `balance` included, which the endpoint rejects with 400 —
      // so every save-confirmation toast was for a save that never landed.
      await api(`/api/admin/users/${editingUser.id}`, {
        method: 'PUT',
        body: JSON.stringify({ email: editingUser.email, phone: editingUser.phone }),
      })
      toast(s.editSuccess, 'success')
      setEditingUser(null)
      reload()
    } catch (err) {
      toast(errMessage(err, s.editError), 'error')
    } finally {
      setSaving(false)
    }
  }

  const filteredUsers = users.filter((u) => {
    if (!userSearch) return true
    const q = userSearch.toLowerCase()
    return (u.email || '').toLowerCase().includes(q) ||
           (u.phone || '').toLowerCase().includes(q) ||
           String(u.id).includes(q)
  })

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <SectionHeader
          title={s.title}
          subtitle={
            total > users.length
              ? s.subtitleShown(f.num(users.length), f.num(total))
              : s.subtitleTotal(f.num(total))
          }
        />
        <RefreshButton onClick={reload} busy={loading} />
      </div>

      {error && <ErrorCard message={error} onRetry={reload} />}
      {!error && !data && <CardSkeleton count={4} />}

      {data && (
        <>
          <div className="admin-card">
            <div style={{ position: 'relative' }}>
              <Icon name="search" size={16} style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
              <input
                className="input w-full"
                placeholder={s.searchPlaceholder}
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
                style={{ paddingRight: '2.5rem' }}
              />
            </div>
          </div>

          <div className="admin-card overflow-x-auto">
            <table className="admin-table w-full text-sm">
              <thead>
                <tr>
                  <th className="text-right p-3">{s.colId}</th>
                  <th className="text-right p-3">{s.colEmail}</th>
                  <th className="text-right p-3">{s.colPhone}</th>
                  <th className="text-right p-3">{s.colBalance}</th>
                  <th className="text-right p-3">{s.colReserved}</th>
                  <th className="text-right p-3">{s.colUsedToday}</th>
                  <th className="text-right p-3">{s.colStatus}</th>
                  <th className="text-right p-3">{s.colActions}</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="p-6 text-center text-sm text-muted">
                      {s.noUsersFound}
                    </td>
                  </tr>
                ) : (
                  filteredUsers.map((u) => (
                    <tr key={u.id} className="cursor-pointer hover:bg-[var(--bg-elevated)]" onClick={() => setDrawerUid(u.id)}>
                      <td className="p-3 text-xs font-mono">{u.id}</td>
                      <td className="p-3 text-sm font-medium text-primary">{u.email}</td>
                      <td className="p-3 text-xs text-secondary">{u.phone || '—'}</td>
                      {/* balance and ledger_sum must be equal -- the append-only
                          ledger invariant. If they ever diverge, a wallet write
                          landed without a matching ledger row (or vice versa),
                          which is a billing-integrity bug. Surface it loudly here
                          rather than silently showing one of the two numbers. */}
                      <td className="p-3 text-xs">
                        {f.price(u.balance)}
                        {u.balance !== u.ledger_sum && (
                          <span className="badge badge-danger mr-1" title={s.ledgerMismatchTitle(f.price(u.ledger_sum))}>
                            {s.ledgerMismatch}
                          </span>
                        )}
                      </td>
                      <td className="p-3 text-xs text-secondary">{u.reserved > 0 ? f.price(u.reserved) : '—'}</td>
                      <td className="p-3 text-xs text-secondary">{f.num(u.used_today)}</td>
                      <td className="p-3">
                        <span className={u.banned ? 'badge badge-danger' : 'badge badge-positive'}>
                          {u.banned ? s.statusBanned : s.statusActive}
                        </span>
                      </td>
                      <td className="p-3">
                        <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                          <button className="btn btn-sm" onClick={() => setEditingUser(u)} title={s.editTitle}>
                            <Icon name="settings" size={14} />
                          </button>
                          <button className="btn btn-sm" onClick={() => setDrawerUid(u.id)} title={s.detailsTitle}>
                            <Icon name="search" size={14} />
                          </button>
                          <button
                            className={u.banned ? 'btn btn-sm' : 'btn btn-sm btn-danger'}
                            onClick={() => toggleBan(u.id)}
                            title={u.banned ? s.unbanTitle : s.banTitle}
                          >
                            <Icon name="security" size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* User Edit Modal — restricted to the fields the server accepts */}
      {editingUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => setEditingUser(null)}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <div className="card relative w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-primary">{s.editModalTitle}</h3>
              <button className="btn btn-icon btn-sm" onClick={() => setEditingUser(null)}>
                <Icon name="close" size={16} />
              </button>
            </div>
            <div className="space-y-3">
              {/* Only the fields PUT /admin/users/{uid} actually accepts are
                  editable here. This modal used to offer a username field and
                  a plan dropdown; neither exists. There is no `username`
                  column on `users`, and a plan is expressed through the
                  `subscriptions` table, not a user column — so both controls
                  wrote into a field the server discarded, and the admin was
                  shown a save confirmation for a change that never happened.
                  `status` is the same trap: AdminUserEdit accepts it and
                  admin_edit_user has no branch for it, so it is silently
                  dropped — deliberately not offered here. */}
              <Field label={s.emailLabel}>
                <input className="input w-full" value={editingUser.email || ''} onChange={(e) => setEditingUser({ ...editingUser, email: e.target.value })} />
              </Field>
              <Field label={s.phoneLabel}>
                <input className="input w-full" dir="ltr" value={editingUser.phone || ''} onChange={(e) => setEditingUser({ ...editingUser, phone: e.target.value })} />
              </Field>
              {/* Direct wallet-balance editing was removed from this modal: the
                  backend now refuses `balance` on PUT /admin/users/{uid}
                  outright (it used to insert an unaudited, non-idempotent
                  ledger row that never touched the wallet table at all --
                  see backend/admin_users.py). Use the drawer's wallet tab. */}
            </div>
            <div className="flex gap-2 mt-5">
              <button className="btn flex-1" onClick={saveUserEdit} disabled={saving}>
                {saving ? (
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                ) : s.save}
              </button>
              <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={() => setEditingUser(null)}>{s.cancel}</button>
            </div>
          </div>
        </div>
      )}

      {/* User Detail Drawer — self-contained, opens from the edge that
          direction puts it on. */}
      {drawerUid != null && (
        <UserDetailDrawer
          api={api}
          uid={drawerUid}
          onClose={() => setDrawerUid(null)}
          onBanToggled={toggleBan}
        />
      )}
    </div>
  )
}
