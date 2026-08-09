'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { Spinner, EmptyState, toast } from '@/components/ui'
import { faPrice, faDate } from '@/lib/format'

type Server = {
  id: number
  hostname: string | null
  ip_address: string | null
  status: 'provisioning' | 'active' | 'suspended' | 'terminated'
  monthly_price_irt: number
  in_sync: boolean
  last_heartbeat_at: string | null
}

const STATUS_LABEL: Record<string, string> = {
  provisioning: 'در حال راه‌اندازی', active: 'فعال', suspended: 'متوقف‌شده', terminated: 'خاتمه‌یافته',
}
const STATUS_BADGE: Record<string, string> = {
  provisioning: 'badge-accent', active: 'badge-positive', suspended: 'badge-warning', terminated: 'badge-danger',
}

export default function HermesServersPage() {
  const { token, user, loading: authLoading } = useAuth()
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
        if (!cancelled) toast('خطا در دریافت سرورها', 'error')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [token])

  if (!authLoading && !user) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '50vh', gap: '1rem' }}>
        <h1 className="page-title">وارد شوید</h1>
        <a href="/login" className="btn btn-primary">ورود به حساب</a>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between slide-up">
        <h1 className="page-title">سرورهای هرمس من</h1>
        <Link href="/hermes" className="btn btn-primary btn-sm">
          <Icon name="plus" size={14} />
          سرور جدید
        </Link>
      </div>

      {loading ? (
        <div className="flex items-center justify-center" style={{ minHeight: '30vh' }}><Spinner size="lg" /></div>
      ) : servers.length === 0 ? (
        <EmptyState icon="rocket" title="هنوز سروری ندارید" description="یک سرور هرمس سفارش دهید تا اینجا نمایش داده شود.">
          <Link href="/hermes" className="btn btn-primary">مشاهده پلن‌ها</Link>
        </EmptyState>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '1rem' }}>
          {servers.map((s, idx) => (
            <Link
              key={s.id}
              href={`/hermes/servers/${s.id}`}
              className="card card-interactive slide-up"
              style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.5rem', animationDelay: `${0.1 + Math.min(idx, 10) * 0.04}s` }}
            >
              <div className="flex items-center justify-between">
                <span style={{ fontWeight: 700 }}>{s.hostname || `سرور #${s.id}`}</span>
                <span className={`badge ${STATUS_BADGE[s.status]}`} style={{ fontSize: '0.6875rem' }}>{STATUS_LABEL[s.status]}</span>
              </div>
              <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', direction: 'ltr', textAlign: 'right' }}>{s.ip_address || '—'}</span>
              <div className="flex items-center justify-between" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                <span>{s.in_sync ? 'همگام' : 'در حال اعمال تغییرات'}</span>
                <span>{faPrice(s.monthly_price_irt)}/ماه</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
