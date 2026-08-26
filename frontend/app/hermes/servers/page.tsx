'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { Spinner, EmptyState, toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { hermesServersStrings } from './page.strings'

type Server = {
  id: number
  hostname: string | null
  ip_address: string | null
  status: 'provisioning' | 'active' | 'suspended' | 'terminated'
  monthly_price_irt: number
  in_sync: boolean
  last_heartbeat_at: string | null
}

const STATUS_BADGE: Record<string, string> = {
  provisioning: 'badge-accent', active: 'badge-positive', suspended: 'badge-warning', terminated: 'badge-danger',
}

export default function HermesServersPage() {
  const { token, user, loading: authLoading } = useAuth()
  const lang = useLang()
  const s = hermesServersStrings(lang)
  const f = fmt(lang)
  const [servers, setServers] = useState<Server[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/api/hermes/servers', { headers: { Authorization: `Bearer ${token}` } })
        if (!res.ok) throw new Error('failed')
        const data = await res.json()
        if (!cancelled) setServers(Array.isArray(data) ? data : [])
      } catch {
        if (!cancelled) toast(s.loadError, 'error')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  if (!authLoading && !user) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '50vh', gap: '1rem' }}>
        <h1 className="page-title">{s.signIn}</h1>
        <a href="/login" className="btn btn-primary">{s.loginToAccount}</a>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="page-title">{s.pageTitle}</h1>
        <Link href="/hermes" className="btn btn-primary btn-sm">
          <Icon name="plus" size={14} />
          {s.newServer}
        </Link>
      </div>

      {loading ? (
        <div className="flex items-center justify-center" style={{ minHeight: '30vh' }}><Spinner size="lg" /></div>
      ) : servers.length === 0 ? (
        <EmptyState icon="rocket" title={s.emptyTitle} description={s.emptyDescription}>
          <Link href="/hermes" className="btn btn-primary">{s.viewPlans}</Link>
        </EmptyState>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '1rem' }}>
          {servers.map((sv) => (
            <Link key={sv.id} href={`/hermes/servers/${sv.id}`} className="card card-interactive" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div className="flex items-center justify-between">
                <span style={{ fontWeight: 700 }}>{sv.hostname || s.serverNumber(f.num(sv.id))}</span>
                <span className={`badge ${STATUS_BADGE[sv.status]}`} style={{ fontSize: '0.6875rem' }}>{s.status[sv.status]}</span>
              </div>
              <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', direction: 'ltr', textAlign: 'right' }}>{sv.ip_address || '—'}</span>
              <div className="flex items-center justify-between" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                <span>{sv.in_sync ? s.inSync : s.syncing}</span>
                <span>{s.perMonth(f.price(sv.monthly_price_irt))}</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
