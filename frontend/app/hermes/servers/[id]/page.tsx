'use client'

import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { Icon } from '@/components/ui/Icon'
import { Spinner, Modal, toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { hermesServerDetailStrings } from './page.strings'

/* ═══════════════════════════════════════════════════════════════
   Server dashboard: connection info, sync status, and skill
   management (add / edit / remove). The "in sync" badge reflects
   desired_state_version vs applied_state_version -- the agent
   daemon on the box is the one that closes that gap, this page
   just declares what should be true.
   ═══════════════════════════════════════════════════════════════ */

type ServerSkill = {
  id: number
  skill_id: string
  options: Record<string, unknown>
  enabled: boolean
  state: 'pending' | 'installed' | 'failed' | 'removing'
  error: string | null
}

type ServerDetail = {
  id: number
  hostname: string | null
  ip_address: string | null
  ssh_port: number
  region: string | null
  status: 'provisioning' | 'active' | 'suspended' | 'terminated'
  monthly_price_irt: number
  paid_through_at: string | null
  agent_token_prefix: string | null
  desired_state_version: number
  applied_state_version: number
  in_sync: boolean
  last_heartbeat_at: string | null
  agent_version: string | null
  skills: ServerSkill[]
}

type CatalogItem = { id: string; name_fa: string; name_en: string }

const SKILL_STATE_BADGE: Record<string, string> = {
  pending: 'badge-accent', installed: 'badge-positive', failed: 'badge-danger', removing: 'aurora-cap-default',
}

export default function HermesServerDetailPage() {
  const params = useParams()
  const serverId = params?.id as string
  const { token, user, loading: authLoading } = useAuth()
  const lang = useLang()
  const s = hermesServerDetailStrings(lang)
  const f = fmt(lang)
  const skillName = (item: CatalogItem) => (lang === 'en' ? item.name_en : item.name_fa)

  const [server, setServer] = useState<ServerDetail | null>(null)
  const [catalog, setCatalog] = useState<CatalogItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)

  const fetchServer = useCallback(async () => {
    if (!token || !serverId) return
    try {
      const res = await fetch(`/api/hermes/servers/${serverId}`, { headers: { Authorization: `Bearer ${token}` } })
      if (!res.ok) throw new Error('failed')
      setServer(await res.json())
    } catch {
      toast(s.loadError, 'error')
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, serverId])

  useEffect(() => { fetchServer() }, [fetchServer])

  useEffect(() => {
    fetch('/api/hermes/skill-catalog').then((r) => r.ok && r.json()).then((d) => setCatalog(Array.isArray(d) ? d : [])).catch(() => {})
  }, [])

  const removeSkill = async (skillId: string) => {
    if (!token || !server) return
    try {
      const res = await apiFetch(`/api/hermes/servers/${server.id}/skills/${skillId}`, {
        method: 'DELETE', headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        toast(data?.detail || s.removeSkillError, 'error')
        return
      }
      toast(s.removeSkillSuccess, 'success')
      fetchServer()
    } catch {
      toast(s.networkError, 'error')
    }
  }

  const toggleSkill = async (skillId: string, enabled: boolean) => {
    if (!token || !server) return
    try {
      const res = await apiFetch(`/api/hermes/servers/${server.id}/skills/${skillId}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ enabled }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        toast(data?.detail || s.updateSkillError, 'error')
        return
      }
      fetchServer()
    } catch {
      toast(s.networkError, 'error')
    }
  }

  if (!authLoading && !user) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '50vh', gap: '1rem' }}>
        <h1 className="page-title">{s.signIn}</h1>
        <a href="/login" className="btn btn-primary">{s.loginToAccount}</a>
      </div>
    )
  }

  if (loading || !server) {
    return <div className="flex items-center justify-center" style={{ minHeight: '40vh' }}><Spinner size="lg" /></div>
  }

  const attachedSkillIds = new Set(server.skills.map((sk) => sk.skill_id))
  const availableToAdd = catalog.filter((c) => !attachedSkillIds.has(c.id))

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-2">
        <Link href="/hermes/servers" className="btn btn-secondary btn-sm"><Icon name="close" size={14} /> {s.back}</Link>
        <h1 className="page-title" style={{ margin: 0 }}>{server.hostname || s.serverNumber(f.num(server.id))}</h1>
      </div>

      {/* ── Connection & status ── */}
      <div className="card" style={{ padding: '1.25rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem' }}>
        <Info label={s.ip} value={server.ip_address ? `${server.ip_address}:${server.ssh_port}` : '—'} ltr />
        <Info label={s.status} value={s.statusLabel[server.status]} />
        <Info label={s.sync} value={server.in_sync ? s.inSync : s.pendingSync(f.num(server.applied_state_version), f.num(server.desired_state_version))} />
        <Info label={s.lastAgentHeartbeat} value={server.last_heartbeat_at ? f.date(server.last_heartbeat_at) : s.neverConnected} />
        <Info label={s.monthlyCost} value={f.price(server.monthly_price_irt)} />
        <Info label={s.paidThrough} value={server.paid_through_at ? f.date(server.paid_through_at) : '—'} />
      </div>

      {/* ── Skills ── */}
      <div className="card" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <div className="flex items-center justify-between">
          <h2 style={{ fontWeight: 700 }}>{s.installedSkills}</h2>
          <button className="btn btn-primary btn-sm" onClick={() => setShowAddModal(true)} disabled={availableToAdd.length === 0}>
            <Icon name="plus" size={14} /> {s.addSkill}
          </button>
        </div>

        {server.skills.length === 0 ? (
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>{s.noSkillsInstalled}</p>
        ) : (
          <div className="flex flex-col gap-2">
            {server.skills.map((sk) => (
              <div key={sk.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.625rem 0.75rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
                <div className="flex items-center gap-2">
                  <span style={{ fontWeight: 600 }}>{(() => { const item = catalog.find((c) => c.id === sk.skill_id); return item ? skillName(item) : sk.skill_id })()}</span>
                  <span className={`badge ${SKILL_STATE_BADGE[sk.state]}`} style={{ fontSize: '0.6875rem' }}>{s.skillState[sk.state]}</span>
                  {sk.error && <span style={{ fontSize: '0.6875rem', color: 'var(--danger)' }}>{sk.error}</span>}
                </div>
                <div className="flex items-center gap-2">
                  <button className="btn btn-secondary btn-sm" onClick={() => toggleSkill(sk.skill_id, !sk.enabled)}>
                    {sk.enabled ? s.disable : s.enable}
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={() => removeSkill(sk.skill_id)} style={{ color: 'var(--danger)' }}>
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <AddSkillModal
        open={showAddModal}
        onClose={() => setShowAddModal(false)}
        options={availableToAdd}
        token={token}
        serverId={server.id}
        onAdded={() => { setShowAddModal(false); fetchServer() }}
      />
    </div>
  )
}

function Info({ label, value, ltr = false }: { label: string; value: string; ltr?: boolean }) {
  return (
    <div>
      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>{label}</span>
      <span style={{ fontWeight: 600, direction: ltr ? 'ltr' : undefined, display: 'inline-block' }}>{value}</span>
    </div>
  )
}

function AddSkillModal({
  open, onClose, options, token, serverId, onAdded,
}: {
  open: boolean
  onClose: () => void
  options: CatalogItem[]
  token: string | null
  serverId: number
  onAdded: () => void
}) {
  const lang = useLang()
  const s = hermesServerDetailStrings(lang)
  const skillName = (item: CatalogItem) => (lang === 'en' ? item.name_en : item.name_fa)
  const [skillId, setSkillId] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => { if (open) setSkillId(options[0]?.id ?? '') }, [open, options])

  const submit = async () => {
    if (!token || !skillId) return
    setSubmitting(true)
    try {
      const res = await apiFetch(`/api/hermes/servers/${serverId}/skills`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ skill_id: skillId, options: {} }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        toast(data?.detail || s.addSkillError, 'error')
        return
      }
      toast(s.addSkillSuccess, 'success')
      onAdded()
    } catch {
      toast(s.networkError, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={s.addSkillModalTitle}>
      <div className="flex flex-col gap-3">
        <select className="input" value={skillId} onChange={(e) => setSkillId(e.target.value)}>
          {options.map((o) => <option key={o.id} value={o.id}>{skillName(o)}</option>)}
        </select>
        <button className="btn btn-primary" disabled={submitting || !skillId} onClick={submit} style={{ justifyContent: 'center' }}>
          {submitting ? <Spinner size="sm" /> : <Icon name="plus" size={16} />}
          {s.add}
        </button>
      </div>
    </Modal>
  )
}
