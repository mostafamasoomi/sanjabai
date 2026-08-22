'use client'

import { useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { faNum, faPrice } from '@/lib/format'
import { SectionHeader, Field } from './shared'
import UserDetailDrawer from './UserDetailDrawer'
import { api } from '../AdminPanel'
import type { UserRow, UserDetail, UserDetailTab } from '../AdminPanel'

/* ═══════════════════════════════════════════════════════════════════════════
   Users — moved verbatim out of AdminPanel.tsx (page === 'users'), later
   updated (2026-08-22) to open a side drawer (UserDetailDrawer.tsx) on row
   click instead of replacing the whole section with a drill-down page.

   The drawer is fully self-contained: it fetches
   detail/ledger/payments/usage/conversations itself via the `api` helper
   (imported the same way UserWalletOps.tsx already does — AdminPanel.tsx
   exports it as a bearer-token-authenticated fetch wrapper; see that file's
   comment for why apiFetch.ts is deliberately not used here). It does NOT
   read AdminPanel's userDetail/userDetailTab/userTabData/loadingDetail
   state — those props are kept in this component's prop type purely so it
   stays call-site-compatible with AdminPanel.tsx (out of scope for this
   change, still passes them); they are otherwise unused now.
   `drawerUid` is new local state owned by this component.

   Ban/unban in the drawer delegates to the `banUser` prop below (unchanged,
   already the correct POST /admin/users/{uid}/ban + list-refresh call) so
   the outer table's badge updates too — the drawer only mirrors the flip
   locally for instant feedback.
   ═══════════════════════════════════════════════════════════════════════════ */

interface UsersSectionProps {
  users: UserRow[]
  userSearch: string
  setUserSearch: (v: string) => void
  editingUser: UserRow | null
  setEditingUser: (u: UserRow | null) => void
  selectedUserId: number | null
  setSelectedUserId: (id: number | null) => void
  userDetail: UserDetail | null
  setUserDetail: (d: UserDetail | null) => void
  userDetailTab: UserDetailTab
  userTabData: any
  setUserTabData: (d: any) => void
  loadingDetail: boolean
  openUserDetail: (uid: number) => void
  loadUserTab: (tab: UserDetailTab) => void
  banUser: (uid: number) => void
  saveUserEdit: () => void
}

export default function UsersSection({
  users, userSearch, setUserSearch, editingUser, setEditingUser, banUser, saveUserEdit,
}: UsersSectionProps) {
  const [drawerUid, setDrawerUid] = useState<number | null>(null)

  const filteredUsers = users.filter(u => {
    if (!userSearch) return true
    const q = userSearch.toLowerCase()
    return (u.email || '').toLowerCase().includes(q) ||
           (u.phone || '').toLowerCase().includes(q) ||
           String(u.id).includes(q)
  })

  return (
    <div className="space-y-4">
      <SectionHeader title="مدیریت کاربران" subtitle={`${faNum(users.length)} کاربر ثبت‌نام شده`} />
      <div className="admin-card">
        <div style={{ position: 'relative' }}>
          <Icon name="search" size={16} style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
          <input
            className="input w-full"
            placeholder="جستجو: ایمیل، موبایل، شناسه..."
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
              <th className="text-right p-3">شناسه</th>
              <th className="text-right p-3">ایمیل</th>
              <th className="text-right p-3">موبایل</th>
              <th className="text-right p-3">موجودی</th>
              <th className="text-right p-3">در رزرو</th>
              <th className="text-right p-3">مصرف امروز</th>
              <th className="text-right p-3">وضعیت</th>
              <th className="text-right p-3">عملیات</th>
            </tr>
          </thead>
          <tbody>
            {filteredUsers.length === 0 ? (
              <tr>
                <td colSpan={8} className="p-6 text-center text-sm text-muted">
                  کاربری یافت نشد
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
                    {faPrice(u.balance)}
                    {u.balance !== u.ledger_sum && (
                      <span className="badge badge-danger mr-1" title={`مجموع دفتر کل: ${faPrice(u.ledger_sum)}`}>
                        ناهمخوان با دفتر کل
                      </span>
                    )}
                  </td>
                  <td className="p-3 text-xs text-secondary">{u.reserved > 0 ? faPrice(u.reserved) : '—'}</td>
                  <td className="p-3 text-xs text-secondary">{faNum(u.used_today)}</td>
                  <td className="p-3">
                    <span className={u.banned ? 'badge badge-danger' : 'badge badge-positive'}>
                      {u.banned ? 'مسدود' : 'فعال'}
                    </span>
                  </td>
                  <td className="p-3">
                    <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                      <button className="btn btn-sm" onClick={() => setEditingUser(u)} title="ویرایش">
                        <Icon name="settings" size={14} />
                      </button>
                      <button className="btn btn-sm" onClick={() => setDrawerUid(u.id)} title="جزئیات">
                        <Icon name="search" size={14} />
                      </button>
                      {!u.banned && (
                        <button className="btn btn-sm btn-danger" onClick={() => banUser(u.id)} title="مسدودسازی">
                          <Icon name="security" size={14} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* User Edit Modal — restricted to the fields the server accepts */}
      {editingUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => setEditingUser(null)}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <div className="card relative w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-primary">ویرایش کاربر</h3>
              <button className="btn btn-icon btn-sm" onClick={() => setEditingUser(null)}>
                <Icon name="close" size={16} />
              </button>
            </div>
            <div className="space-y-3">
              {/* Only the fields PUT /admin/users/{uid} actually accepts are
                  editable here. This modal used to offer "نام کاربری" and a
                  "پلن" dropdown; neither exists. There is no `username`
                  column on `users`, and a plan is expressed through the
                  `subscriptions` table, not a user column — so both controls
                  wrote into a field the server discarded, and the admin was
                  shown a save confirmation for a change that never happened.
                  `status` is the same trap: AdminUserEdit accepts it and
                  admin_edit_user has no branch for it, so it is silently
                  dropped — deliberately not offered here. */}
              <Field label="ایمیل">
                <input className="input w-full" value={editingUser.email || ''} onChange={(e) => setEditingUser({ ...editingUser, email: e.target.value })} />
              </Field>
              <Field label="موبایل">
                <input className="input w-full" dir="ltr" value={editingUser.phone || ''} onChange={(e) => setEditingUser({ ...editingUser, phone: e.target.value })} />
              </Field>
              {/* Direct wallet-balance editing was removed from this modal: the
                  backend now refuses `balance` on PUT /admin/users/{uid}
                  outright (it used to insert an unaudited, non-idempotent
                  ledger row that never touched the wallet table at all --
                  see backend/admin.py). Use the drawer's کیف پول tab instead. */}
            </div>
            <div className="flex gap-2 mt-5">
              <button className="btn flex-1" onClick={saveUserEdit}>ذخیره</button>
              <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={() => setEditingUser(null)}>انصراف</button>
            </div>
          </div>
        </div>
      )}

      {/* User Detail Drawer — self-contained, opens from the left (RTL) */}
      {drawerUid != null && (
        <UserDetailDrawer
          api={api}
          uid={drawerUid}
          onClose={() => setDrawerUid(null)}
          onBanToggled={banUser}
        />
      )}
    </div>
  )
}
