'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt, dirFor } from '@/lib/i18n'
import { StatCard, Field } from './shared'
import UserWalletOps from './UserWalletOps'
import type { UserDetail } from '../AdminPanel'
import {
  LedgerTab, PaymentsTab, UsageTab, ConversationsTab,
  type TabState, type LedgerPayload, type PaymentsPayload,
  type UsagePayload, type ConversationsPayload,
} from './UserDetailTabs'
import { userDetailDrawerStrings } from './UserDetailDrawer.strings'

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
  const lang = useLang()
  const s = userDetailDrawerStrings(lang)
  const f = fmt(lang)

  const TAB_LABEL: Record<DrawerTab, string> = {
    overview: s.tabOverview, wallet: s.tabWallet, payments: s.tabPayments,
    usage: s.tabUsage, conversations: s.tabConversations, actions: s.tabActions,
  }

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

  // Always the LATEST `uid` prop, updated synchronously every render (not
  // just in an effect) so an in-flight request started for a previous user
  // can tell, the moment it resolves, whether the drawer has since moved on
  // to a different user -- see loadDetail/loadTab below.
  const uidRef = useRef(uid)
  uidRef.current = uid

  const loadDetail = useCallback(async () => {
    const requestedUid = uid
    setDetailStatus('loading')
    setDetailError('')
    try {
      const res = await api(`/api/admin/users/${requestedUid}/detail`)
      const data: UserDetail = await res.json()
      if (uidRef.current !== requestedUid) return // a different user is open now — discard
      setDetail(data)
      setEditEmail(data.user.email || '')
      setEditPhone(data.user.phone || '')
      setEditDailyLimit(data.quota ? String(data.quota.daily_limit) : '')
      setDetailStatus('ready')
    } catch (e) {
      if (uidRef.current !== requestedUid) return
      setDetailStatus('error')
      setDetailError(errMessage(e, s.fetchError))
    }
  }, [api, uid, s])

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

  // One shape shared by the four data-heavy tabs below (ledger/payments/
  // usage/conversations) -- was four copy-pasted loaders that only differed
  // in the endpoint suffix, the setState call, and the response->payload
  // mapping. `transform` turns the raw JSON body into the tab's payload
  // type; the stale-uid guard mirrors loadDetail's above.
  const loadTab = useCallback(async <T,>(
    endpointSuffix: string,
    setState: (s: TabState<T>) => void,
    transform: (json: any) => T,
    fallback: string,
  ) => {
    const requestedUid = uid
    setState({ status: 'loading', data: null, error: '' })
    try {
      const res = await api(`/api/admin/users/${requestedUid}/${endpointSuffix}`)
      const j = await res.json()
      if (uidRef.current !== requestedUid) return
      setState({ status: 'ready', data: transform(j), error: '' })
    } catch (e) {
      if (uidRef.current !== requestedUid) return
      setState({ status: 'error', data: null, error: errMessage(e, fallback) })
    }
  }, [api, uid])

  const openTab = (t: DrawerTab) => {
    setTab(t)
    if (t === 'wallet' && ledgerState.status === 'idle') {
      loadTab<LedgerPayload>('ledger', setLedgerState, (j) => ({ items: j.items || [], total: j.total || 0 }), s.ledgerFetchError)
    }
    if (t === 'payments' && paymentsState.status === 'idle') {
      loadTab<PaymentsPayload>('payments', setPaymentsState, (j) => ({ payments: j.payments || [], subscriptions: j.subscriptions || [] }), s.paymentsFetchError)
    }
    if (t === 'usage' && usageState.status === 'idle') {
      loadTab<UsagePayload>('usage', setUsageState, (j) => ({ by_model: j.by_model || [], daily: j.daily || [] }), s.usageFetchError)
    }
    if (t === 'conversations' && convState.status === 'idle') {
      loadTab<ConversationsPayload>('conversations', setConvState, (j) => ({ items: j.items || [], total: j.total || 0 }), s.conversationsFetchError)
    }
  }

  // Ban/unban delegates the network call to AdminPanel's banUser (keeps the
  // outer list's badge in sync); this only mirrors the flip locally for
  // instant feedback in the drawer. `onBanToggled` is typed `=> void` but
  // AdminPanel's actual banUser is an async function that awaits the
  // network call before returning -- `await`ing it here (Promise.resolve
  // handles a genuinely void-returning caller too) keeps `banBusy` true,
  // and the double-click guard armed, until that call has actually
  // settled, not just until this synchronous function returns.
  const toggleBan = async () => {
    if (!detail || banBusy) return
    setBanBusy(true)
    const prevBanned = detail.user.banned
    setDetail({ ...detail, user: { ...detail.user, banned: !prevBanned } })
    try {
      await Promise.resolve(onBanToggled(uid))
    } catch {
      // Defensive: today's banUser (AdminPanel.tsx) catches its own errors
      // and always resolves, so this branch isn't exercised by the current
      // prop -- but a future implementation that does reject must not
      // leave the optimistic flip standing.
      setDetail((d) => (d ? { ...d, user: { ...d.user, banned: prevBanned } } : d))
    } finally {
      setBanBusy(false)
    }
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
        toast(s.dailyLimitInvalid, 'error')
        return
      }
      if (!detail.quota || n !== detail.quota.daily_limit) body.daily_limit = Math.trunc(n)
    }
    if (Object.keys(body).length === 0) {
      toast(s.noChangesToSave, 'info')
      return
    }
    setEditSaving(true)
    try {
      await api(`/api/admin/users/${uid}`, { method: 'PUT', body: JSON.stringify(body) })
      toast(s.saveSuccess, 'success')
      await loadDetail()
    } catch (e) {
      toast(errMessage(e, s.saveError), 'error')
    } finally {
      setEditSaving(false)
    }
  }

  const u = detail?.user

  return (
    <div className="fixed inset-0 z-50" dir={dirFor(lang)}>
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
              <h2 className="font-bold text-primary truncate">{u?.display_name || u?.email || s.userFallback(f.num(uid))}</h2>
              <p className="text-xs text-muted truncate">{u?.email || '—'} · {s.idPrefix(f.num(uid))}</p>
            </div>
            {u && (
              <span className={u.banned ? 'badge badge-danger' : 'badge badge-positive'}>
                {u.banned ? s.statusBanned : s.statusActive}
              </span>
            )}
          </div>
          <button className="btn btn-icon btn-sm flex-shrink-0" onClick={onClose} aria-label={s.close}>
            <Icon name="close" size={16} />
          </button>
        </div>

        {detailStatus === 'loading' && <div className="skeleton h-40 w-full rounded mt-4" />}
        {detailStatus === 'error' && (
          <div className="mt-4 space-y-2">
            <p className="text-sm text-danger">{detailError || s.fetchError}</p>
            <button className="btn btn-sm" onClick={loadDetail}>{s.retry}</button>
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
                    <StatCard icon="wallet" label={s.statWalletBalance} value={f.price(detail.wallet.balance)} color="#22c55e" />
                    <StatCard icon="lock" label={s.statReserved} value={f.price(detail.wallet.reserved)} color="#f59e0b" />
                    <StatCard icon="chat" label={s.statConversations} value={f.num(detail.stats.conversation_count)} color="#a855f7" />
                    <StatCard icon="pricing" label={s.statTotalCost} value={f.price(detail.stats.total_cost)} color="#f59e0b" />
                    <StatCard icon="wallet" label={s.statVerifiedPayments} value={f.price(detail.stats.total_payments)} color="#06b6d4" />
                    <StatCard icon="models" label={s.statTotalTokens} value={f.num(detail.stats.total_tokens)} color="#3b82f6" />
                  </div>
                  <div className="admin-card">
                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div><span className="text-muted">{s.fieldName}</span><p className="font-medium">{u.display_name || '—'}</p></div>
                      <div><span className="text-muted">{s.fieldEmail}</span><p className="font-medium">{u.email || '—'}</p></div>
                      <div><span className="text-muted">{s.fieldPhone}</span><p className="font-medium">{u.phone || '—'}</p></div>
                      <div><span className="text-muted">{s.fieldTelegram}</span><p className="font-medium">{u.telegram_id || '—'}</p></div>
                      <div><span className="text-muted">{s.fieldDailyLimit}</span><p className="font-medium">{detail.quota ? f.num(detail.quota.daily_limit) : '—'}</p></div>
                      <div><span className="text-muted">{s.fieldUsedToday}</span><p className="font-medium">{detail.quota ? f.num(detail.quota.used_today) : f.num(0)}</p></div>
                      <div><span className="text-muted">{s.fieldJoinedAt}</span><p className="font-medium">{f.date(u.created_at)}</p></div>
                      <div>
                        <span className="text-muted">{s.fieldPanel}</span>
                        {/* There is no `role` column on users (see
                            backend/admin_user_ops.py's comment) -- the
                            closest analog is this preferences.panel flag,
                            changed from the wallet tab. */}
                        <p className="font-medium">{String(u.preferences?.panel || '') === 'developer' ? s.panelDeveloper : s.panelConsumer}</p>
                      </div>
                    </div>
                    {String(u.preferences?.ai_personality || '') && (
                      <div className="mt-3 p-3 rounded-lg text-xs" style={{ background: 'var(--bg-elevated)' }}>
                        <span className="font-bold text-accent">{s.aiPersonalityLabel}</span>
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
                    <h3 className="text-sm font-bold text-primary mb-2">{s.walletHistoryTitle}</h3>
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
                    <h3 className="text-sm font-bold text-primary mb-3">{s.banSectionTitle}</h3>
                    <div className="flex items-center gap-3">
                      <button
                        className={`btn btn-sm ${u.banned ? '' : 'btn-danger'}`}
                        disabled={banBusy}
                        onClick={toggleBan}
                      >
                        <Icon name="security" size={14} />
                        {u.banned ? s.unbanUser : s.banUser}
                      </button>
                      <span className="text-xs text-muted">
                        {s.currentStatus(u.banned ? s.statusBanned : s.statusActive)}
                      </span>
                    </div>
                  </div>

                  <div className="admin-card">
                    <h3 className="text-sm font-bold text-primary mb-3">{s.editInfoTitle}</h3>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <Field label={s.emailField}>
                        <input className="input w-full" value={editEmail} onChange={(e) => setEditEmail(e.target.value)} dir="ltr" />
                      </Field>
                      <Field label={s.phoneField}>
                        <input className="input w-full" value={editPhone} onChange={(e) => setEditPhone(e.target.value)} dir="ltr" />
                      </Field>
                      <Field label={s.dailyLimitField}>
                        <input className="input w-full" inputMode="numeric" value={editDailyLimit} onChange={(e) => setEditDailyLimit(e.target.value)} />
                      </Field>
                    </div>
                    <p className="text-xs text-muted mt-2">
                      {s.walletEditNote}
                    </p>
                    <button className="btn btn-sm mt-3" onClick={saveEdit} disabled={editSaving}>
                      {editSaving ? s.savingLabel : s.saveChanges}
                    </button>
                  </div>

                  <div className="admin-card">
                    <h3 className="text-sm font-bold text-primary mb-2">{s.panelMoveTitle}</h3>
                    <p className="text-xs text-muted">
                      {s.panelMoveNote}
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
