'use client'

import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { Spinner, Modal, toast } from '@/components/ui'
import { faPrice, faDate, faNum } from '@/lib/format'

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

type CatalogItem = { id: string; name_fa: string }

const SKILL_STATE_LABEL: Record<string, string> = {
  pending: 'در حال اعمال', installed: 'نصب‌شده', failed: 'خطا', removing: 'در حال حذف',
}
const SKILL_STATE_BADGE: Record<string, string> = {
  pending: 'badge-accent', installed: 'badge-positive', failed: 'badge-danger', removing: 'aurora-cap-default',
}

export default function HermesServerDetailPage() {
  const params = useParams()
  const serverId = params?.id as string
  const { token, user, loading: authLoading } = useAuth()

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
      toast('خطا در دریافت اطلاعات سرور', 'error')
    } finally {
      setLoading(false)
    }
  }, [token, serverId])

  useEffect(() => { fetchServer() }, [fetchServer])

  useEffect(() => {
    fetch('/api/hermes/skill-catalog').then((r) => r.ok && r.json()).then((d) => setCatalog(Array.isArray(d) ? d : [])).catch(() => {})
  }, [])

  const removeSkill = async (skillId: string) => {
    if (!token || !server) return
    try {
      const res = await fetch(`/api/hermes/servers/${server.id}/skills/${skillId}`, {
        method: 'DELETE', headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        toast(data?.detail || 'خطا در حذف اسکیل', 'error')
        return
      }
      toast('درخواست حذف اسکیل ثبت شد', 'success')
      fetchServer()
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    }
  }

  const toggleSkill = async (skillId: string, enabled: boolean) => {
    if (!token || !server) return
    try {
      const res = await fetch(`/api/hermes/servers/${server.id}/skills/${skillId}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ enabled }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        toast(data?.detail || 'خطا در بروزرسانی اسکیل', 'error')
        return
      }
      fetchServer()
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    }
  }

  if (!authLoading && !user) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '50vh', gap: '1rem' }}>
        <h1 className="page-title">وارد شوید</h1>
        <a href="/login" className="btn btn-primary">ورود به حساب</a>
      </div>
    )
  }

  if (loading || !server) {
    return <div className="flex items-center justify-center" style={{ minHeight: '40vh' }}><Spinner size="lg" /></div>
  }

  const attachedSkillIds = new Set(server.skills.map((s) => s.skill_id))
  const availableToAdd = catalog.filter((c) => !attachedSkillIds.has(c.id))

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-2 slide-up">
        <Link href="/hermes/servers" className="btn btn-secondary btn-sm"><Icon name="close" size={14} /> بازگشت</Link>
        <h1 className="page-title" style={{ margin: 0 }}>{server.hostname || `سرور #${server.id}`}</h1>
      </div>

      {/* ── Connection & status ── */}
      <div className="card slide-up" style={{ padding: '1.25rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem', animationDelay: '0.05s' }}>
        <Info label="آی‌پی" value={server.ip_address ? `${server.ip_address}:${server.ssh_port}` : '—'} ltr />
        <Info label="وضعیت" value={server.status === 'active' ? 'فعال' : server.status === 'suspended' ? 'متوقف‌شده' : server.status === 'provisioning' ? 'در حال راه‌اندازی' : 'خاتمه‌یافته'} />
        <Info label="همگام‌سازی" value={server.in_sync ? 'همگام' : `در انتظار (${faNum(server.applied_state_version)}/${faNum(server.desired_state_version)})`} />
        <Info label="آخرین اتصال ایجنت" value={server.last_heartbeat_at ? faDate(server.last_heartbeat_at) : 'هنوز متصل نشده'} />
        <Info label="هزینه ماهانه" value={faPrice(server.monthly_price_irt)} />
        <Info label="پرداخت‌شده تا" value={server.paid_through_at ? faDate(server.paid_through_at) : '—'} />
      </div>

      {/* ── Skills ── */}
      <div className="card slide-up" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.75rem', animationDelay: '0.1s' }}>
        <div className="flex items-center justify-between">
          <h2 style={{ fontWeight: 700 }}>اسکیل‌های نصب‌شده</h2>
          <button className="btn btn-primary btn-sm" onClick={() => setShowAddModal(true)} disabled={availableToAdd.length === 0}>
            <Icon name="plus" size={14} /> افزودن اسکیل
          </button>
        </div>

        {server.skills.length === 0 ? (
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>هنوز اسکیلی روی این سرور نصب نشده است.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {server.skills.map((s, idx) => (
              <div
                key={s.id}
                className="slide-up"
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '0.625rem 0.75rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
                  animationDelay: `${0.15 + Math.min(idx, 10) * 0.02}s`,
                }}
              >
                <div className="flex items-center gap-2">
                  <span style={{ fontWeight: 600 }}>{catalog.find((c) => c.id === s.skill_id)?.name_fa || s.skill_id}</span>
                  <span className={`badge ${SKILL_STATE_BADGE[s.state]}`} style={{ fontSize: '0.6875rem' }}>{SKILL_STATE_LABEL[s.state]}</span>
                  {s.error && <span style={{ fontSize: '0.6875rem', color: 'var(--danger)' }}>{s.error}</span>}
                </div>
                <div className="flex items-center gap-2">
                  <button className="btn btn-secondary btn-sm" onClick={() => toggleSkill(s.skill_id, !s.enabled)}>
                    {s.enabled ? 'غیرفعال کردن' : 'فعال کردن'}
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={() => removeSkill(s.skill_id)} style={{ color: 'var(--danger)' }}>
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
  const [skillId, setSkillId] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => { if (open) setSkillId(options[0]?.id ?? '') }, [open, options])

  const submit = async () => {
    if (!token || !skillId) return
    setSubmitting(true)
    try {
      const res = await fetch(`/api/hermes/servers/${serverId}/skills`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ skill_id: skillId, options: {} }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        toast(data?.detail || 'خطا در افزودن اسکیل', 'error')
        return
      }
      toast('اسکیل به سرور اضافه شد', 'success')
      onAdded()
    } catch {
      toast('خطا در ارتباط با سرور', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="افزودن اسکیل">
      <div className="flex flex-col gap-3">
        <select className="input" value={skillId} onChange={(e) => setSkillId(e.target.value)}>
          {options.map((o) => <option key={o.id} value={o.id}>{o.name_fa}</option>)}
        </select>
        <button className="btn btn-primary" disabled={submitting || !skillId} onClick={submit} style={{ justifyContent: 'center' }}>
          {submitting ? <Spinner size="sm" /> : <Icon name="plus" size={16} />}
          افزودن
        </button>
      </div>
    </Modal>
  )
}
