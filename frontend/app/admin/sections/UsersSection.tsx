'use client'

import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { StatCard, SectionHeader, Field } from './shared'
import type { UserRow, UserDetail, UserDetailTab } from '../AdminPanel'

/* ═══════════════════════════════════════════════════════════════════════════
   Users — moved verbatim out of AdminPanel.tsx (page === 'users', both the
   list view and the drill-down detail view). All state and handlers still
   live in AdminPanel; this component is purely presentational so navigating
   away and back preserves in-progress search text / edit modal / drill-down
   exactly like before the split.
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
  users, userSearch, setUserSearch, editingUser, setEditingUser,
  selectedUserId, setSelectedUserId, userDetail, setUserDetail,
  userDetailTab, userTabData, setUserTabData, loadingDetail,
  openUserDetail, loadUserTab, banUser, saveUserEdit,
}: UsersSectionProps) {
  if (!selectedUserId) {
    return (
      <div className="space-y-4">
        <SectionHeader title="مدیریت کاربران" subtitle={`${faNum(users.length)} کاربر ثبت‌نام شده`} />
        <div className="admin-card">
          <div style={{ position: 'relative' }}>
            <Icon name="search" size={16} style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
            <input
              className="input w-full"
              placeholder="جستجو: ایمیل، نام، شناسه..."
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
                <th className="text-right p-3">نام کاربری</th>
                <th className="text-right p-3">ایمیل</th>
                <th className="text-right p-3">پلن</th>
                <th className="text-right p-3">موجودی</th>
                <th className="text-right p-3">وضعیت</th>
                <th className="text-right p-3">عملیات</th>
              </tr>
            </thead>
            <tbody>
              {users.filter(u => {
                if (!userSearch) return true
                const q = userSearch.toLowerCase()
                return (u.username || '').toLowerCase().includes(q) ||
                       (u.email || '').toLowerCase().includes(q) ||
                       String(u.id).includes(q)
              }).length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-6 text-center text-sm text-muted">
                    کاربری یافت نشد
                  </td>
                </tr>
              ) : (
                users.filter(u => {
                  if (!userSearch) return true
                  const q = userSearch.toLowerCase()
                  return (u.username || '').toLowerCase().includes(q) ||
                         (u.email || '').toLowerCase().includes(q) ||
                         String(u.id).includes(q)
                }).map((u) => (
                  <tr key={u.id} className="cursor-pointer hover:bg-[var(--bg-elevated)]" onClick={() => openUserDetail(u.id)}>
                    <td className="p-3 text-xs font-mono">{u.id}</td>
                    <td className="p-3 text-sm font-medium text-primary">{u.username || '—'}</td>
                    <td className="p-3 text-xs text-secondary">{u.email}</td>
                    <td className="p-3">
                      <span className="badge badge-accent">{u.plan || 'رایگان'}</span>
                    </td>
                    <td className="p-3 text-xs">{faNum(u.wallet_balance)}</td>
                    <td className="p-3">
                      <span className={u.is_active ? 'badge badge-positive' : 'badge badge-danger'}>
                        {u.is_active ? 'فعال' : 'غیرفعال'}
                      </span>
                    </td>
                    <td className="p-3">
                      <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                        <button className="btn btn-sm" onClick={() => setEditingUser(u)} title="ویرایش">
                          <Icon name="settings" size={14} />
                        </button>
                        <button className="btn btn-sm" onClick={() => openUserDetail(u.id)} title="جزئیات">
                          <Icon name="search" size={14} />
                        </button>
                        {u.is_active && (
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

        {/* User Edit Modal */}
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
                <Field label="نام کاربری">
                  <input className="input w-full" value={editingUser.username || ''} onChange={(e) => setEditingUser({ ...editingUser, username: e.target.value })} />
                </Field>
                <Field label="ایمیل">
                  <input className="input w-full" value={editingUser.email || ''} onChange={(e) => setEditingUser({ ...editingUser, email: e.target.value })} />
                </Field>
                <Field label="پلن">
                  <select className="input w-full" value={editingUser.plan || ''} onChange={(e) => setEditingUser({ ...editingUser, plan: e.target.value })}>
                    <option value="">رایگان</option>
                    <option value="pro">Pro</option>
                    <option value="enterprise">Enterprise</option>
                  </select>
                </Field>
                <Field label="موجودی کیف پول">
                  <input className="input w-full" type="number" value={editingUser.wallet_balance || 0} onChange={(e) => setEditingUser({ ...editingUser, wallet_balance: +e.target.value })} />
                </Field>
              </div>
              <div className="flex gap-2 mt-5">
                <button className="btn flex-1" onClick={saveUserEdit}>ذخیره</button>
                <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={() => setEditingUser(null)}>انصراف</button>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button className="btn btn-ghost btn-sm" onClick={() => { setSelectedUserId(null); setUserDetail(null); setUserTabData(null) }}>
          <Icon name="close" size={14} /> بازگشت
        </button>
        <SectionHeader title={`کاربر #${selectedUserId}`} subtitle={userDetail?.user?.email || ''} />
      </div>

      {loadingDetail && !userDetail && (
        <div className="admin-card"><div className="skeleton h-40 w-full rounded" /></div>
      )}

      {userDetail && (
        <>
          {/* Stat Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
            <StatCard icon="wallet" label="موجودی" value={faNum(userDetail.balance)} color="#22c55e" />
            <StatCard icon="models" label="توکن مصرفی" value={faNum(userDetail.stats.total_tokens)} color="#3b82f6" />
            <StatCard icon="chat" label="گفتگوها" value={userDetail.stats.conversation_count} color="#a855f7" />
            <StatCard icon="pricing" label="هزینه کل" value={faNum(userDetail.stats.total_cost)} color="#f59e0b" />
            <StatCard icon="wallet" label="پرداخت‌ها" value={userDetail.stats.payment_count} color="#06b6d4" />
            <StatCard icon="dashboard" label="درخواست‌ها" value={userDetail.stats.usage_events} color="#ec4899" />
          </div>

          {/* User Info Card */}
          <div className="admin-card">
            <div className="flex items-start gap-4">
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center text-2xl font-bold" style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}>
                {(userDetail.user.display_name || userDetail.user.email || '?')[0].toUpperCase()}
              </div>
              <div className="flex-1 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
                <div><span className="text-muted">نام</span><p className="font-medium">{userDetail.user.display_name || '—'}</p></div>
                <div><span className="text-muted">ایمیل</span><p className="font-medium">{userDetail.user.email || '—'}</p></div>
                <div><span className="text-muted">تلگرام</span><p className="font-medium">{userDetail.user.telegram_id || '—'}</p></div>
                <div><span className="text-muted">تلفن</span><p className="font-medium">{userDetail.user.phone || '—'}</p></div>
                <div><span className="text-muted">کیف پول</span><p className="font-medium">{faNum(userDetail.wallet.balance)} (رزرو: {faNum(userDetail.wallet.reserved)})</p></div>
                <div><span className="text-muted">سهمیه روزانه</span><p className="font-medium">{faNum(userDetail.quota?.daily_limit) || '—'}</p></div>
                <div><span className="text-muted">مصرف امروز</span><p className="font-medium">{faNum(userDetail.quota?.used_today, { fallback: '۰' })}</p></div>
                <div><span className="text-muted">عضویت</span><p className="font-medium">{new Date(userDetail.user.created_at).toLocaleDateString('fa-IR')}</p></div>
              </div>
            </div>
            {String(userDetail.user.preferences?.ai_personality || '') && (
              <div className="mt-3 p-3 rounded-lg text-xs" style={{ background: 'var(--bg-elevated)' }}>
                <span className="font-bold text-accent">🧠 Soul: </span>
                <span className="text-secondary">{String(userDetail.user.preferences.ai_personality)}</span>
              </div>
            )}
          </div>

          {/* Tabs */}
          <div className="flex gap-1 border-b" style={{ borderColor: 'var(--border)' }}>
            {(['overview', 'conversations', 'usage', 'ledger', 'payments'] as UserDetailTab[]).map(tab => (
              <button
                key={tab}
                className={`px-4 py-2 text-xs font-medium transition-colors ${userDetailTab === tab ? 'border-b-2' : 'opacity-60 hover:opacity-100'}`}
                style={userDetailTab === tab ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : { color: 'var(--text-secondary)' }}
                onClick={() => loadUserTab(tab)}
              >
                {{ overview: 'نمای کلی', conversations: 'گفتگوها', usage: 'مصرف توکن', ledger: 'تراکنش‌ها', payments: 'پرداخت‌ها' }[tab]}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="admin-card min-h-[200px]">
            {loadingDetail && <div className="skeleton h-32 w-full rounded" />}
            {!loadingDetail && userDetailTab === 'overview' && (
              <div className="text-sm text-secondary">
                <p>از تب‌های بالا برای مشاهده جزئیات استفاده کنید.</p>
              </div>
            )}
            {!loadingDetail && userDetailTab === 'conversations' && userTabData && (
              <div className="overflow-x-auto">
                <table className="admin-table w-full text-sm">
                  <thead><tr>
                    <th className="text-right p-2">شناسه</th><th className="text-right p-2">عنوان</th>
                    <th className="text-right p-2">مدل</th><th className="text-right p-2">پیامها</th>
                    <th className="text-right p-2">تاریخ</th>
                  </tr></thead>
                  <tbody>
                    {(userTabData?.items || []).map((c: any) => (
                      <tr key={c.id}>
                        <td className="p-2 text-xs font-mono">{c.id}</td>
                        <td className="p-2 text-xs">{c.title}</td>
                        <td className="p-2 text-xs"><span className="badge badge-accent">{c.model || '—'}</span></td>
                        <td className="p-2 text-xs">{c.msg_count || '—'}</td>
                        <td className="p-2 text-xs">{new Date(c.updated_at).toLocaleDateString('fa-IR')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-xs mt-2 text-muted">
                  {(userTabData?.total || 0)} گفتگو
                </p>
              </div>
            )}
            {!loadingDetail && userDetailTab === 'usage' && userTabData && (
              <div className="space-y-4">
                <h3 className="text-sm font-bold text-primary">مصرف بر اساس مدل</h3>
                <table className="admin-table w-full text-sm">
                  <thead><tr>
                    <th className="text-right p-2">مدل</th><th className="text-right p-2">درخواست</th>
                    <th className="text-right p-2">ورودی</th><th className="text-right p-2">خروجی</th>
                    <th className="text-right p-2">هزینه</th><th className="text-right p-2">آخرین استفاده</th>
                  </tr></thead>
                  <tbody>
                    {(userTabData?.by_model || []).map((m: any, i: number) => (
                      <tr key={i}>
                        <td className="p-2 text-xs font-medium">{m.model}</td>
                        <td className="p-2 text-xs">{m.calls}</td>
                        <td className="p-2 text-xs">{faNum(m.input_tokens || 0)}</td>
                        <td className="p-2 text-xs">{faNum(m.output_tokens || 0)}</td>
                        <td className="p-2 text-xs">{faNum(m.total_cost || 0)}</td>
                        <td className="p-2 text-xs">{m.last_used ? new Date(m.last_used).toLocaleDateString('fa-IR') : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {!loadingDetail && userDetailTab === 'ledger' && userTabData && (
              <div className="overflow-x-auto">
                <table className="admin-table w-full text-sm">
                  <thead><tr>
                    <th className="text-right p-2">شناسه</th><th className="text-right p-2">مبلغ</th>
                    <th className="text-right p-2">مانده</th><th className="text-right p-2">شرح</th>
                    <th className="text-right p-2">تاریخ</th>
                  </tr></thead>
                  <tbody>
                    {(userTabData?.items || []).map((l: any) => (
                      <tr key={l.id}>
                        <td className="p-2 text-xs font-mono">{l.id}</td>
                        <td className={`p-2 text-xs font-bold ${l.amount >= 0 ? 'text-green-400' : 'text-red-400'}`}>{l.amount >= 0 ? '+' : ''}{faNum(l.amount)}</td>
                        <td className="p-2 text-xs">{faNum(l.balance_after)}</td>
                        <td className="p-2 text-xs">{l.reason}</td>
                        <td className="p-2 text-xs">{new Date(l.created_at).toLocaleDateString('fa-IR')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-xs mt-2 text-muted">
                  {(userTabData?.total || 0)} تراکنش
                </p>
              </div>
            )}
            {!loadingDetail && userDetailTab === 'payments' && userTabData && (
              <div className="space-y-4">
                <h3 className="text-sm font-bold text-primary">پرداخت‌ها</h3>
                <table className="admin-table w-full text-sm">
                  <thead><tr>
                    <th className="text-right p-2">شناسه</th><th className="text-right p-2">مبلغ</th>
                    <th className="text-right p-2">وضعیت</th><th className="text-right p-2">نوع</th>
                    <th className="text-right p-2">کد مرجع</th><th className="text-right p-2">تاریخ</th>
                  </tr></thead>
                  <tbody>
                    {(userTabData?.payments || []).map((p: any) => (
                      <tr key={p.id}>
                        <td className="p-2 text-xs font-mono">{p.id}</td>
                        <td className="p-2 text-xs font-bold">{faNum(p.amount)}</td>
                        <td className="p-2"><span className={`badge ${p.status === 'verified' ? 'badge-positive' : p.status === 'pending' ? 'badge-accent' : 'badge-danger'}`}>{p.status === 'verified' ? 'تایید شده' : p.status === 'pending' ? 'در انتظار' : 'ناموفق'}</span></td>
                        <td className="p-2 text-xs">{p.payment_type}</td>
                        <td className="p-2 text-xs font-mono">{p.ref_id || '—'}</td>
                        <td className="p-2 text-xs">{new Date(p.created_at).toLocaleDateString('fa-IR')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {(userTabData?.subscriptions || []).length > 0 && (
                  <>
                    <h3 className="text-sm font-bold text-primary">اشتراکها</h3>
                    <table className="admin-table w-full text-sm">
                      <thead><tr>
                        <th className="text-right p-2">پلن</th><th className="text-right p-2">وضعیت</th>
                        <th className="text-right p-2">شروع</th><th className="text-right p-2">پایان</th>
                        <th className="text-right p-2">مبلغ</th>
                      </tr></thead>
                      <tbody>
                        {(userTabData?.subscriptions || []).map((s: any, i: number) => (
                          <tr key={i}>
                            <td className="p-2 text-xs font-medium">{s.plan}</td>
                            <td className="p-2"><span className={`badge ${s.status === 'active' ? 'badge-positive' : 'badge-accent'}`}>{s.status === 'active' ? 'فعال' : s.status}</span></td>
                            <td className="p-2 text-xs">{new Date(s.starts_at).toLocaleDateString('fa-IR')}</td>
                            <td className="p-2 text-xs">{s.ends_at ? new Date(s.ends_at).toLocaleDateString('fa-IR') : '—'}</td>
                            <td className="p-2 text-xs">{faNum(s.price_paid)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
