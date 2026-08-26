'use client'

import { useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { SectionHeader, Field } from './shared'
import { ErrorCard, RefreshButton, CardSkeleton } from './LoadState'
import ModerationRules from './ModerationRules'
import { api, errMessage } from '../api'
import { useAdminResource } from '../useAdminResource'
import {
  DECISION_BADGE, SEVERITY_COLOR, SEVERITY_ORDER, severityLabel, decisionLabel, actionLabel,
  type ModerationDecision, type ModerationEvent, type ModerationEventsPayload,
  type ModerationUserAction, type ModerationUserRisk,
} from './moderationTypes'
import { moderationSectionStrings } from './ModerationSection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Moderation (Phase J) — owner demand was: a user searching for prohibited
   content must be caught, must raise an alert, and an admin must be able to
   stop it, all from this panel.

   Contract is frozen (backend/admin_moderation.py, landing alongside this):
     GET    /admin/moderation/events?page&limit&severity&decision&q
     GET    /admin/moderation/rules              -- rule CRUD lives in
     POST   /admin/moderation/rules[/{id}]           ./ModerationRules.tsx
     DELETE /admin/moderation/rules/{id}
     GET    /admin/moderation/users/{uid}         -- risk_score, event_count, recent
     POST   /admin/moderation/users/{uid}/action  { action, reason }
   Every path above carries the `/api` prefix a section once shipped
   without, leaving it unreachable in production for months.

   This is the most sensitive screen in the product. It renders only the
   `snippet` the backend already decided is safe to show an admin — never
   the user's full message, and there is deliberately no "show full message"
   affordance anywhere on this screen, including the risk modal below.
   ═══════════════════════════════════════════════════════════════════════════ */

const EVENTS_PAGE_SIZE = 20
const SEVERITY_OPTIONS = ['', ...SEVERITY_ORDER]
const DECISION_OPTIONS: ('' | ModerationDecision)[] = ['', 'allow', 'flag', 'block']

type Tab = 'queue' | 'rules'

export default function ModerationSection() {
  const lang = useLang()
  const s = moderationSectionStrings(lang)
  const f = fmt(lang)
  const [tab, setTab] = useState<Tab>('queue')
  const [page, setPage] = useState(1)
  const [severity, setSeverity] = useState('')
  const [decision, setDecision] = useState<'' | ModerationDecision>('')
  const [qInput, setQInput] = useState('')
  const [appliedQ, setAppliedQ] = useState('')
  const [riskUid, setRiskUid] = useState<number | null>(null)
  const [riskEmail, setRiskEmail] = useState('')

  const params = new URLSearchParams({ page: String(page), limit: String(EVENTS_PAGE_SIZE) })
  if (severity) params.set('severity', severity)
  if (decision) params.set('decision', decision)
  if (appliedQ) params.set('q', appliedQ)

  const { data, error, loading, reload } = useAdminResource<ModerationEventsPayload>(
    `/api/admin/moderation/events?${params.toString()}`,
    (raw) => ({
      items: raw?.items || [], total: raw?.total ?? 0,
      page: raw?.page ?? page, limit: raw?.limit ?? EVENTS_PAGE_SIZE,
    }),
    s.eventsLoadError,
  )

  const changeSeverity = (v: string) => { setSeverity(v); setPage(1) }
  const changeDecision = (v: '' | ModerationDecision) => { setDecision(v); setPage(1) }
  const applySearch = () => { setAppliedQ(qInput.trim()); setPage(1) }

  const events = data?.items || []
  const total = data?.total || 0
  const pageCount = Math.max(1, Math.ceil(total / EVENTS_PAGE_SIZE))

  const openRisk = (ev: ModerationEvent) => { setRiskUid(ev.user_id); setRiskEmail(ev.user_email) }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <SectionHeader title={s.title} subtitle={s.subtitle} />
        {tab === 'queue' && <RefreshButton onClick={reload} busy={loading} />}
      </div>

      <div className="flex gap-2">
        <button
          className={`btn btn-sm ${tab === 'queue' ? 'font-bold' : ''}`}
          style={{ background: tab === 'queue' ? 'var(--accent-dim)' : 'var(--bg-elevated)', color: tab === 'queue' ? 'var(--accent)' : 'var(--text-secondary)' }}
          onClick={() => setTab('queue')}
        >
          {s.tabQueue}
        </button>
        <button
          className={`btn btn-sm ${tab === 'rules' ? 'font-bold' : ''}`}
          style={{ background: tab === 'rules' ? 'var(--accent-dim)' : 'var(--bg-elevated)', color: tab === 'rules' ? 'var(--accent)' : 'var(--text-secondary)' }}
          onClick={() => setTab('rules')}
        >
          {s.tabRules}
        </button>
      </div>

      {tab === 'rules' && <ModerationRules />}

      {tab === 'queue' && (
        <>
          <div className="admin-card">
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
              <Field label={s.severityLabel}>
                <select className="input w-full" value={severity} onChange={(e) => changeSeverity(e.target.value)}>
                  {SEVERITY_OPTIONS.map((sv) => <option key={sv || 'all'} value={sv}>{sv ? severityLabel(sv, lang) : s.allOption}</option>)}
                </select>
              </Field>
              <Field label={s.decisionLabel}>
                <select className="input w-full" value={decision} onChange={(e) => changeDecision(e.target.value as '' | ModerationDecision)}>
                  {DECISION_OPTIONS.map((d) => <option key={d || 'all'} value={d}>{d ? decisionLabel(d, lang) : s.allOption}</option>)}
                </select>
              </Field>
              <div className="sm:col-span-2">
                <Field label={s.searchLabel}>
                  <div className="flex gap-2">
                    <input
                      className="input w-full" value={qInput} onChange={(e) => setQInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && applySearch()} placeholder={s.searchPlaceholder}
                    />
                    <button className="btn btn-sm" onClick={applySearch}><Icon name="search" size={14} /></button>
                  </div>
                </Field>
              </div>
            </div>
          </div>

          {error && <ErrorCard message={error} onRetry={reload} />}
          {!error && !data && <CardSkeleton count={4} />}

          {data && (
            <div className="admin-card overflow-x-auto">
              <table className="admin-table w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-right p-3">{s.colUser}</th>
                    <th className="text-right p-3">{s.colCategory}</th>
                    <th className="text-right p-3">{s.colSeverity}</th>
                    <th className="text-right p-3">{s.colDecision}</th>
                    <th className="text-right p-3">{s.colSnippet}</th>
                    <th className="text-right p-3">{s.colTime}</th>
                  </tr>
                </thead>
                <tbody>
                  {events.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-6 text-center text-sm text-muted">{s.noEvents}</td>
                    </tr>
                  ) : (
                    events.map((ev) => (
                      <tr key={ev.id} className="cursor-pointer hover:bg-[var(--bg-elevated)]" onClick={() => openRisk(ev)}>
                        <td className="p-3 text-xs text-secondary">{ev.user_email || `#${ev.user_id}`}</td>
                        <td className="p-3 text-xs text-secondary">{ev.category || '—'}</td>
                        <td className="p-3">
                          <span
                            className="badge"
                            style={{ background: `${SEVERITY_COLOR[ev.severity] ?? '#666'}20`, color: SEVERITY_COLOR[ev.severity] ?? 'var(--text-secondary)' }}
                          >
                            {severityLabel(ev.severity, lang)}
                          </span>
                        </td>
                        <td className="p-3"><span className={`badge ${DECISION_BADGE[ev.decision] ?? 'badge-accent'}`}>{decisionLabel(ev.decision, lang)}</span></td>
                        <td className="p-3 text-xs text-secondary break-words max-w-sm">{ev.snippet}</td>
                        <td className="p-3 text-xs text-muted">{f.date(ev.created_at)} {f.time(ev.created_at)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>

              {total > EVENTS_PAGE_SIZE && (
                <div className="flex items-center justify-between mt-4 pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
                  <span className="text-xs text-muted">{s.pageInfo(f.num(page), f.num(pageCount), f.num(total))}</span>
                  <div className="flex gap-2">
                    <button className="btn btn-sm" disabled={page <= 1 || loading} onClick={() => setPage(Math.max(1, page - 1))}>{s.prevPage}</button>
                    <button className="btn btn-sm" disabled={page >= pageCount || loading} onClick={() => setPage(page + 1)}>{s.nextPage}</button>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {riskUid != null && <UserRiskModal uid={riskUid} email={riskEmail} onClose={() => setRiskUid(null)} />}
    </div>
  )
}

/* ─── Per-user risk view — opened by clicking a row in the queue above ─── */

function UserRiskModal({ uid, email, onClose }: { uid: number; email: string; onClose: () => void }) {
  const lang = useLang()
  const s = moderationSectionStrings(lang)
  const f = fmt(lang)
  const { data, error, loading, reload: load } = useAdminResource<ModerationUserRisk>(
    `/api/admin/moderation/users/${uid}`,
    (raw) => raw,
    s.riskLoadError,
  )
  const [pendingAction, setPendingAction] = useState<ModerationUserAction | null>(null)
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Each of the three actions requires a typed reason first — the submit
  // button stays disabled until `reason.trim()` is non-empty.
  const submitAction = async () => {
    if (!pendingAction || !reason.trim()) return
    setSubmitting(true)
    try {
      await api(`/api/admin/moderation/users/${uid}/action`, {
        method: 'POST',
        body: JSON.stringify({ action: pendingAction, reason: reason.trim() }),
      })
      toast(s.actionRecorded(actionLabel(pendingAction, lang)), 'success')
      setPendingAction(null)
      setReason('')
      load() // refetch after mutation — an action that doesn't move risk_score reads as a no-op
    } catch (err) {
      toast(errMessage(err, s.actionError), 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div className="card relative w-full max-w-lg max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-primary">{s.riskModalTitle(email || s.userFallback(f.num(uid)))}</h3>
          <button className="btn btn-icon btn-sm" onClick={onClose}><Icon name="close" size={16} /></button>
        </div>

        {error && <ErrorCard message={error} onRetry={load} />}
        {!error && !data && loading && <CardSkeleton count={2} />}

        {data && (
          <>
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div className="admin-card">
                <p className="text-xs text-muted mb-1">{s.riskScore}</p>
                <p className="text-xl font-bold text-primary">{f.num(data.risk_score)}</p>
              </div>
              <div className="admin-card">
                <p className="text-xs text-muted mb-1">{s.eventCount}</p>
                <p className="text-xl font-bold text-primary">{f.num(data.event_count)}</p>
              </div>
            </div>

            <p className="text-xs font-medium text-secondary mb-2">{s.recentEvents}</p>
            {(data.recent || []).length === 0 ? (
              <div className="text-center py-4 text-xs text-muted mb-4">{s.noRecentEvents}</div>
            ) : (
              <div className="space-y-2 mb-4">
                {data.recent.map((ev) => (
                  <div key={ev.id} className="text-xs p-2 rounded-lg" style={{ background: 'var(--bg-elevated)' }}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`badge ${DECISION_BADGE[ev.decision] ?? 'badge-accent'}`}>{decisionLabel(ev.decision, lang)}</span>
                      <span className="text-muted">{ev.category || '—'}</span>
                      <span className="text-muted mr-auto">{f.date(ev.created_at)}</span>
                    </div>
                    <p className="text-secondary break-words">{ev.snippet}</p>
                  </div>
                ))}
              </div>
            )}

            <p className="text-xs font-medium text-secondary mb-2">{s.userAction}</p>
            <div className="flex gap-2 mb-3">
              {(['warn', 'restrict', 'suspend'] as ModerationUserAction[]).map((a) => (
                <button
                  key={a}
                  className={`btn btn-sm ${pendingAction === a ? 'font-bold' : ''}`}
                  style={{ background: pendingAction === a ? 'var(--accent-dim)' : 'var(--bg-elevated)', color: pendingAction === a ? 'var(--accent)' : 'var(--text-secondary)' }}
                  onClick={() => setPendingAction(a)}
                >
                  {actionLabel(a, lang)}
                </button>
              ))}
            </div>

            {pendingAction && (
              <div className="space-y-2">
                <Field label={s.reasonLabel(actionLabel(pendingAction, lang))}>
                  <textarea className="input w-full" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={s.reasonPlaceholder} />
                </Field>
                <div className="flex gap-2">
                  <button className="btn flex-1" onClick={submitAction} disabled={submitting || !reason.trim()}>
                    {submitting ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" /> : s.submitAction}
                  </button>
                  <button className="btn btn-sm" style={{ background: 'var(--bg-elevated)' }} onClick={() => { setPendingAction(null); setReason('') }}>{s.cancel}</button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
