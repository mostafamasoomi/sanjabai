'use client'

import { useCallback, useEffect, useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faNum, faPrice, faDate } from '@/lib/format'
import { StatCard, Field } from './shared'
import UserWalletOps from './UserWalletOps'
import type { UserDetail } from '../AdminPanel'
import {
  LedgerTab, PaymentsTab, UsageTab, ConversationsTab,
  type TabState, type LedgerPayload, type PaymentsPayload,
  type UsagePayload, type ConversationsPayload,
} from './UserDetailTabs'

/* ═══════════════════════════════════════════════════════════════════════════
   UserDetailDrawer — side drawer for a single user, opened from a row click
   in UsersSection.tsx. RTL layout, so the drawer is anchored to the LEFT
   edge of the viewport (the far side from where RTL text starts) rather
   than the right, matching how side panels sit in this admin's other RTL
   screens.

   Self-contained per the PackagesSection/MarkupSection pattern: receives
   only `api`, fetches everything itself, keyed off `uid`. Does NOT read or
   write AdminPanel.tsx's userDetail/userTabData state (that state still
   exists for backward compatibility — AdminPanel.tsx is out of scope for
   this change — but this component ignores it entirely and is the
   presentation now used from UsersSection.tsx).

   Backend contract (backend/admin.py, backend/admin_user_ops.py):
     GET  /admin/users/{uid}/detail        -> UserDetail (see AdminPanel.tsx)
     GET  /admin/users/{uid}/ledger        -> lazy-loaded on the کیف‌پول tab
     GET  /admin/users/{uid}/payments      -> lazy-loaded on پرداخت‌ها
     GET  /admin/users/{uid}/usage         -> lazy-loaded on مصرف
     GET  /admin/users/{uid}/conversations -> lazy-loaded on گفتگوها
     POST /admin/users/{uid}/ban           -> delegated to the `onBanToggled`
                                               prop (= AdminPanel's banUser),
                                               which also refreshes the
                                               user list's row -- calling it
                                               a second time here would
                                               double-toggle.
     PUT  /admin/users/{uid}               <- {email?, phone?, daily_limit?}
                                               `balance` is never sent: the
                                               backend rejects it outright
                                               (see admin.py's comment) and
                                               wallet changes go through
                                               UserWalletOps's
                                               wallet-adjust call instead.
     POST /admin/users/{uid}/panel         -> handled entirely inside the
                                               reused <UserWalletOps/>, shown
                                               on the کیف پول tab.

   Money is integer toman everywhere; every amount renders through
   faPrice, every count through faNum -- never a raw number, never a
   division/multiplication by 10.
   ═══════════════════════════════════════════════════════════════════════════ */

type ApiFn = (path: string, opts?: RequestInit) => Promise<Response>
type DrawerTab = 'overview' | 'wallet' | 'payments' | 'usage' | 'conversations' | 'actions'

const TAB_LABEL: Record<DrawerTab, string> = {
  overview: 'نمای کلی', wallet: 'کیف پول', payments: 'پرداخت‌ها',
  usage: 'مصرف', conversations: 'گفتگوها', actions: 'اقدامات',
}
const TAB_ORDER: DrawerTab[] = ['overview', 'wallet', 'payments', 'usage', 'conversations', 'actions']

function idleState<T>(): TabState<T> {
  return { status: 'idle', data: null, error: '' }
}

function errMessage(e: unknown, fallback: string): string {
  if (e instanceof Error && e.message && e.message !== 'unauthorized') return e.message
  return fallback
}

interface UserDetailDrawerProps {
  api: ApiFn
  uid: number
  onClose: () => void
  /** AdminPanel's existing banUser(uid) — reused so the outer user list's
      badge refreshes too. Toasts on its own; this component must not also
      call POST /ban directly, or the ban would double-toggle. */
  onBanToggled: (uid: number) => void
}

export default function UserDetailDrawer({ api, uid, onClose, onBanToggled }: UserDetailDrawerProps) {
  const [detail, setDetail] = useState<UserDetail | null>(null)
  const [detailStatus, setDetailStatus] = useState<'loading' | 'error' | 'ready'>('loading')
  const [detailError, setDetailError] = useState('')
  const [tab, setTab] = useState<DrawerTab>('overview')

  const [ledgerState, setLedgerState] = useState<TabState<LedgerPayload>>(idleState)
  const [paymentsState, setPaymentsState] = useState<TabState<PaymentsPayload>>(idleState)
  const [usageState, setUsageState] = useState<TabState<UsagePayload>>(idleState)
  const [convState, setConvState] = useState<TabState<ConversationsPayload>>(idleState)

  const [editEmail, setEditEmail] = useState('')
  const [editPhone, setEditPhone] = useState('')
  const [editDailyLimit, setEditDailyLimit] = useState('')
  const [editSaving, setEditSaving] = useState(false)
  const [banBusy, setBanBusy] = useState(false)

  const loadDetail = useCallback(async () => {
    setDetailStatus('loading')
    setDetailError('')
    try {
      const res = await api(`/api/admin/users/${uid}/detail`)
      const data: UserDetail = await res.json()
      setDetail(data)
      setEditEmail(data.user.email || '')
      setEditPhone(data.user.phone || '')
      setEditDailyLimit(data.quota ? String(data.quota.daily_limit) : '')
      setDetailStatus('ready')
    } catch (e) {
      setDetailStatus('error')
      setDetailError(errMessage(e, 'خطا در دریافت اطلاعات کاربر'))
    }
  }, [api, uid])

  // Reset everything and reload whenever a different user is opened.
  useEffect(() => {
    setTab('overview')
    setLedgerState(idleState())
    setPaymentsState(idleState())
    setUsageState(idleState())
    setConvState(idleState())
    loadDetail()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uid])

  const loadLedger = useCallback(async () => {
    setLedgerState({ status: 'loading', data: null, error: '' })
    try {
      const res = await api(`/api/admin/users/${uid}/ledger`)
      const j = await res.json()
      setLedgerState({ status: 'ready', data: { items: j.items || [], total: j.total || 0 }, error: '' })
    } catch (e) {
      setLedgerState({ status: 'error', data: null, error: errMessage(e, 'خطا در دریافت تراکنش‌ها') })
    }
  }, [api, uid])

  const loadPayments = useCallback(async () => {
    setPaymentsState({ status: 'loading', data: null, error: '' })
    try {
      const res = await api(`/api/admin/users/${uid}/payments`)
      const j = await res.json()
      setPaymentsState({
        status: 'ready',
        data: { payments: j.payments || [], subscriptions: j.subscriptions || [] },
        error: '',
      })
    } catch (e) {
      setPaymentsState({ status: 'error', data: null, error: errMessage(e, 'خطا در دریافت پرداخت‌ها') })
    }
  }, [api, uid])

  const loadUsage = useCallback(async () => {
    setUsageState({ status: 'loading', data: null, error: '' })
    try {
      const res = await api(`/api/admin/users/${uid}/usage`)
      const j = await res.json()
      setUsageState({ status: 'ready', data: { by_model: j.by_model || [], daily: j.daily || [] }, error: '' })
    } catch (e) {
      setUsageState({ status: 'error', data: null, error: errMessage(e, 'خطا در دریافت مصرف') })
    }
  }, [api, uid])

  const loadConversations = useCallback(async () => {
    setConvState({ status: 'loading', data: null, error: '' })
    try {
      const res = await api(`/api/admin/users/${uid}/conversations`)
      const j = await res.json()
      setConvState({ status: 'ready', data: { items: j.items || [], total: j.total || 0 }, error: '' })
    } catch (e) {
      setConvState({ status: 'error', data: null, error: errMessage(e, 'خطا در دریافت گفتگوها') })
    }
  }, [api, uid])

  const openTab = (t: DrawerTab) => {
    setTab(t)
    if (t === 'wallet' && ledgerState.status === 'idle') loadLedger()
    if (t === 'payments' && paymentsState.status === 'idle') loadPayments()
    if (t === 'usage' && usageState.status === 'idle') loadUsage()
    if (t === 'conversations' && convState.status === 'idle') loadConversations()
  }

  // Ban/unban delegates the network call to AdminPanel's banUser (keeps the
  // outer list's badge in sync); this only mirrors the flip locally for
  // instant feedback in the drawer.
  const toggleBan = () => {
    if (!detail || banBusy) return
    setBanBusy(true)
    onBanToggled(uid)
    setDetail({ ...detail, user: { ...detail.user, banned: !detail.user.banned } })
    setBanBusy(false)
  }

  const saveEdit = async () => {
    if (!detail) return
    const body: Record<string, unknown> = {}
    if (editEmail.trim() !== (detail.user.email || '')) body.email = editEmail.trim()
    if (editPhone.trim() !== (detail.user.phone || '')) body.phone = editPhone.trim()
    const dl = editDailyLimit.trim()
    if (dl !== '') {
      const n = Number(dl)
      if (!Number.isFinite(n) || n < 0) {
        toast('سقف روزانه باید عدد صحیح و غیرمنفی باشد', 'error')
        return
      }
      if (!detail.quota || n !== detail.quota.daily_limit) body.daily_limit = Math.trunc(n)
    }
    if (Object.keys(body).length === 0) {
      toast('تغییری برای ذخیره وجود ندارد', 'info')
      return
    }
    setEditSaving(true)
    try {
      await api(`/api/admin/users/${uid}`, { method: 'PUT', body: JSON.stringify(body) })
      toast('اطلاعات کاربر بروزرسانی شد', 'success')
      await loadDetail()
    } catch (e) {
      toast(errMessage(e, 'خطا در ذخیره اطلاعات کاربر'), 'error')
    } finally {
      setEditSaving(false)
    }
  }

  const u = detail?.user

  return (
    <div className="fixed inset-0 z-50" dir="rtl">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div
        className="card absolute top-0 bottom-0 flex flex-col fade-in"
        style={{ left: 0, width: 'min(560px, 100vw)', borderRadius: 0, borderLeft: 'none', overflowY: 'auto' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 pb-4 border-b" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center text-xl font-bold flex-shrink-0" style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}>
              {(u?.display_name || u?.email || '?')[0]?.toUpperCase()}
            </div>
            <div className="min-w-0">
              <h2 className="font-bold text-primary truncate">{u?.display_name || u?.email || `کاربر #${faNum(uid)}`}</h2>
              <p className="text-xs text-muted truncate">{u?.email || '—'} · شناسه {faNum(uid)}</p>
            </div>
            {u && (
              <span className={u.banned ? 'badge badge-danger' : 'badge badge-positive'}>
                {u.banned ? 'مسدود' : 'فعال'}
              </span>
            )}
          </div>
          <button className="btn btn-icon btn-sm flex-shrink-0" onClick={onClose} aria-label="بستن">
            <Icon name="close" size={16} />
          </button>
        </div>

        {detailStatus === 'loading' && <div className="skeleton h-40 w-full rounded mt-4" />}
        {detailStatus === 'error' && (
          <div className="mt-4 space-y-2">
            <p className="text-sm text-danger">{detailError || 'خطا در دریافت اطلاعات کاربر'}</p>
            <button className="btn btn-sm" onClick={loadDetail}>تلاش دوباره</button>
          </div>
        )}

        {detailStatus === 'ready' && detail && u && (
          <>
            {/* Tabs */}
            <div className="flex gap-1 border-b overflow-x-auto mt-3" style={{ borderColor: 'var(--border)' }}>
              {TAB_ORDER.map((t) => (
                <button
                  key={t}
                  className={`px-3 py-2 text-xs font-medium whitespace-nowrap transition-colors ${tab === t ? 'border-b-2' : 'opacity-60 hover:opacity-100'}`}
                  style={tab === t ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : { color: 'var(--text-secondary)' }}
                  onClick={() => openTab(t)}
                >
                  {TAB_LABEL[t]}
                </button>
              ))}
            </div>

            <div className="pt-4 flex-1">
              {tab === 'overview' && (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <StatCard icon="wallet" label="موجودی کیف پول" value={faPrice(detail.wallet.balance)} color="#22c55e" />
                    <StatCard icon="lock" label="رزرو شده" value={faPrice(detail.wallet.reserved)} color="#f59e0b" />
                    <StatCard icon="chat" label="گفتگوها" value={faNum(detail.stats.conversation_count)} color="#a855f7" />
                    <StatCard icon="pricing" label="هزینه کل" value={faPrice(detail.stats.total_cost)} color="#f59e0b" />
                    <StatCard icon="wallet" label="پرداخت‌های تایید شده" value={faPrice(detail.stats.total_payments)} color="#06b6d4" />
                    <StatCard icon="models" label="توکن مصرفی" value={faNum(detail.stats.total_tokens)} color="#3b82f6" />
                  </div>
                  <div className="admin-card">
                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div><span className="text-muted">نام</span><p className="font-medium">{u.display_name || '—'}</p></div>
                      <div><span className="text-muted">ایمیل</span><p className="font-medium">{u.email || '—'}</p></div>
                      <div><span className="text-muted">تلفن</span><p className="font-medium">{u.phone || '—'}</p></div>
                      <div><span className="text-muted">تلگرام</span><p className="font-medium">{u.telegram_id || '—'}</p></div>
                      <div><span className="text-muted">سقف روزانه</span><p className="font-medium">{detail.quota ? faNum(detail.quota.daily_limit) : '—'}</p></div>
                      <div><span className="text-muted">مصرف امروز</span><p className="font-medium">{detail.quota ? faNum(detail.quota.used_today) : '۰'}</p></div>
                      <div><span className="text-muted">تاریخ عضویت</span><p className="font-medium">{faDate(u.created_at)}</p></div>
                      <div>
                        <span className="text-muted">پنل</span>
                        {/* There is no `role` column on users (see
                            backend/admin_user_ops.py's comment) -- the
                            closest analog is this preferences.panel flag,
                            changed from the کیف پول tab. */}
                        <p className="font-medium">{String(u.preferences?.panel || '') === 'developer' ? 'توسعه‌دهنده' : 'مصرف‌کننده'}</p>
                      </div>
                    </div>
                    {String(u.preferences?.ai_personality || '') && (
                      <div className="mt-3 p-3 rounded-lg text-xs" style={{ background: 'var(--bg-elevated)' }}>
                        <span className="font-bold text-accent">شخصیت هوش مصنوعی: </span>
                        <span className="text-secondary">{String(u.preferences.ai_personality)}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {tab === 'wallet' && (
                <div className="space-y-4">
                  <UserWalletOps
                    uid={uid}
                    balance={detail.wallet.balance}
                    panel={String(u.preferences?.panel || '')}
                    onChanged={loadDetail}
                  />
                  <div className="admin-card">
                    <h3 className="text-sm font-bold text-primary mb-2">تاریخچه تراکنش‌های کیف پول</h3>
                    <LedgerTab state={ledgerState} />
                  </div>
                </div>
              )}

              {tab === 'payments' && <div className="admin-card"><PaymentsTab state={paymentsState} /></div>}
              {tab === 'usage' && <div className="admin-card"><UsageTab state={usageState} /></div>}
              {tab === 'conversations' && <div className="admin-card"><ConversationsTab state={convState} /></div>}

              {tab === 'actions' && (
                <div className="space-y-5">
                  <div className="admin-card">
                    <h3 className="text-sm font-bold text-primary mb-3">مسدودسازی</h3>
                    <div className="flex items-center gap-3">
                      <button
                        className={`btn btn-sm ${u.banned ? '' : 'btn-danger'}`}
                        disabled={banBusy}
                        onClick={toggleBan}
                      >
                        <Icon name="security" size={14} />
                        {u.banned ? 'رفع مسدودیت' : 'مسدود کردن کاربر'}
                      </button>
                      <span className="text-xs text-muted">
                        وضعیت فعلی: {u.banned ? 'مسدود' : 'فعال'}
                      </span>
                    </div>
                  </div>

                  <div className="admin-card">
                    <h3 className="text-sm font-bold text-primary mb-3">ویرایش اطلاعات کاربر</h3>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <Field label="ایمیل">
                        <input className="input w-full" value={editEmail} onChange={(e) => setEditEmail(e.target.value)} dir="ltr" />
                      </Field>
                      <Field label="تلفن">
                        <input className="input w-full" value={editPhone} onChange={(e) => setEditPhone(e.target.value)} dir="ltr" />
                      </Field>
                      <Field label="سقف روزانه (تعداد درخواست)">
                        <input className="input w-full" inputMode="numeric" value={editDailyLimit} onChange={(e) => setEditDailyLimit(e.target.value)} />
                      </Field>
                    </div>
                    <p className="text-xs text-muted mt-2">
                      ویرایش مستقیم موجودی کیف پول از این فرم ممکن نیست — از تب «کیف پول» استفاده کنید.
                    </p>
                    <button className="btn btn-sm mt-3" onClick={saveEdit} disabled={editSaving}>
                      {editSaving ? 'در حال ذخیره...' : 'ذخیره تغییرات'}
                    </button>
                  </div>

                  <div className="admin-card">
                    <h3 className="text-sm font-bold text-primary mb-2">جابه‌جایی پنل</h3>
                    <p className="text-xs text-muted">
                      انتقال بین پنل مصرف‌کننده و توسعه‌دهنده از تب «کیف پول» انجام می‌شود.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
