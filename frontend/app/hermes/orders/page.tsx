'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { Spinner, EmptyState, toast } from '@/components/ui'
import { faPrice, faDate } from '@/lib/format'

type Order = {
  id: number
  offering_id: string
  status: 'pending_payment' | 'paid' | 'provisioning' | 'active' | 'suspended' | 'cancelled' | 'expired'
  setup_price_irt: number
  monthly_price_irt: number
  created_at: string
  delivered_at: string | null
}

const STATUS_LABEL: Record<string, string> = {
  pending_payment: 'در انتظار پرداخت',
  paid: 'پرداخت شد — در صف تحویل',
  provisioning: 'در حال راه‌اندازی',
  active: 'فعال',
  suspended: 'متوقف‌شده',
  cancelled: 'لغوشده',
  expired: 'منقضی‌شده',
}

const STATUS_BADGE: Record<string, string> = {
  pending_payment: 'aurora-cap-default',
  paid: 'badge-accent',
  provisioning: 'badge-accent',
  active: 'badge-positive',
  suspended: 'badge-warning',
  cancelled: 'badge-danger',
  expired: 'badge-danger',
}

export default function HermesOrdersPage() {
  const { token, user, loading: authLoading } = useAuth()
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/api/hermes/orders', { headers: { Authorization: `Bearer ${token}` } })
        if (!res.ok) throw new Error('failed')
        const data = await res.json()
        if (!cancelled) setOrders(Array.isArray(data) ? data : [])
      } catch {
        if (!cancelled) toast('خطا در دریافت سفارش‌ها', 'error')
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
      <div className="flex items-center justify-between">
        <h1 className="page-title">سفارش‌های سرور هرمس</h1>
        <Link href="/hermes" className="btn btn-primary btn-sm">
          <Icon name="plus" size={14} />
          سفارش جدید
        </Link>
      </div>

      {loading ? (
        <div className="flex items-center justify-center" style={{ minHeight: '30vh' }}><Spinner size="lg" /></div>
      ) : orders.length === 0 ? (
        <EmptyState icon="rocket" title="هنوز سفارشی ثبت نکرده‌اید" description="یک سرور هرمس سفارش دهید تا اینجا نمایش داده شود.">
          <Link href="/hermes" className="btn btn-primary">مشاهده پلن‌ها</Link>
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-3">
          {orders.map((o) => (
            <div key={o.id} className="card" style={{ padding: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <span style={{ fontWeight: 700 }}>سفارش #{o.id}</span>
                  <span className={`badge ${STATUS_BADGE[o.status] || 'aurora-cap-default'}`} style={{ fontSize: '0.6875rem' }}>
                    {STATUS_LABEL[o.status] || o.status}
                  </span>
                </div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{faDate(o.created_at)}</span>
              </div>
              <div className="flex items-center gap-4">
                <span style={{ fontWeight: 600 }}>{faPrice(o.setup_price_irt + o.monthly_price_irt)}</span>
                {o.status === 'active' && (
                  <Link href="/hermes/servers" className="btn btn-secondary btn-sm">مشاهده سرور</Link>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
