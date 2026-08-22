'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { ApiKeyRevealModal } from '@/components/ApiKeyRevealModal'

// Shared Persian message for the (expected-rare) CSRF-rejection path — the
// backend returns 403 with "هدر X-Requested-With ارسال نشده" if a mutating
// request ever reaches it without the header apiFetch adds automatically.
const FORBIDDEN_MESSAGE = 'درخواست شما رد شد (خطای امنیتی). لطفاً صفحه را تازه‌سازی کرده و دوباره تلاش کنید.'

type ApiKeyInfo = {
  id: number
  name: string
  prefix: string
  active: boolean
  last_used: string | null
  created_at: string | null
  usage_count?: number
}

export default function ApiKeysPage() {
  const { user, token } = useAuth()
  const router = useRouter()
  const [keys, setKeys] = useState<ApiKeyInfo[]>([])
  const [name, setName] = useState('Default')
  const [loading, setLoading] = useState(false)
  const [rotatingId, setRotatingId] = useState<number | null>(null)

  // The one moment the raw key exists in this UI at all: right after a
  // create or rotate response. Never derived from the key list.
  const [reveal, setReveal] = useState<{ key: string; isRotation: boolean } | null>(null)

  useEffect(() => {
    if (user && token) fetchKeys()
  }, [user, token])

  const fetchKeys = async () => {
    try {
      const r = await fetch('/api/api-keys', { headers: { Authorization: `Bearer ${token}` } })
      if (r.status === 401) { router.push('/login'); return }
      if (r.ok) setKeys(await r.json())
    } catch {}
  }

  const generateKey = async () => {
    setLoading(true)
    try {
      const r = await apiFetch('/api/api-keys', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name }),
      })
      if (r.status === 401) { router.push('/login'); return }
      if (r.status === 403) { toast(FORBIDDEN_MESSAGE, 'error'); return }
      const data = await r.json()
      if (r.ok) {
        setReveal({ key: data.key, isRotation: false })
        fetchKeys()
      } else {
        toast(data.detail || 'خطا', 'error')
      }
    } catch {
      toast('خطا در ارتباط', 'error')
    } finally {
      setLoading(false)
    }
  }

  const rotateKey = async (id: number) => {
    if (!confirm('با چرخاندن این کلید، کلید فعلی بلافاصله از کار می‌افتد و باید کلید جدید را در همه جا جایگزین کنید. ادامه می‌دهید؟')) return
    setRotatingId(id)
    try {
      const r = await apiFetch(`/api/api-keys/${id}/rotate`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (r.status === 401) { router.push('/login'); return }
      if (r.status === 403) { toast(FORBIDDEN_MESSAGE, 'error'); return }
      const data = await r.json()
      if (r.ok) {
        setReveal({ key: data.key, isRotation: true })
        fetchKeys()
      } else {
        toast(data.detail || 'خطا', 'error')
      }
    } catch {
      toast('خطا در ارتباط', 'error')
    } finally {
      setRotatingId(null)
    }
  }

  const revokeKey = async (id: number) => {
    try {
      const r = await apiFetch(`/api/api-keys/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (r.status === 401) { router.push('/login'); return }
      if (r.status === 403) { toast(FORBIDDEN_MESSAGE, 'error'); return }
      if (r.ok) {
        toast('کلید غیرفعال شد', 'success')
        fetchKeys()
      }
    } catch {
      toast('خطا', 'error')
    }
  }

  const formatDate = (s: string | null) => {
    if (!s) return '—'
    return new Date(s).toLocaleDateString('fa-IR', { year: 'numeric', month: 'short', day: 'numeric' })
  }

  return (
    <div className="apikeys-page">
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
        <div className="apikeys-header-icon">
          <Icon name="key" size={20} className="text-accent" />
        </div>
        <div>
          <h1 className="page-title">کلیدهای API</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 2 }}>مدیریت کلیدهای دسترسی به API</p>
        </div>
      </div>

      {/* Generate new key */}
      <div className="card apikeys-generate-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Icon name="plus" size={16} className="text-accent" />
          <h2 className="card-title">ساخت کلید جدید</h2>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="نام کلید (مثلاً Production)"
            className="input flex-1"
          />
          <button onClick={generateKey} disabled={loading} className="btn btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            {loading ? (
              <span className="apikeys-spinner" />
            ) : (
              <Icon name="key" size={14} />
            )}
            ساخت کلید
          </button>
        </div>
      </div>

      {/* Existing keys */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Icon name="key" size={16} className="text-accent" />
            <h2 className="card-title">کلیدهای شما</h2>
            {keys.length > 0 && (
              <span className="badge badge-accent">{faNum(keys.length)}</span>
            )}
          </div>
        </div>

        {keys.length === 0 ? (
          <div className="apikeys-empty">
            <div className="apikeys-empty-icon">
              <Icon name="key" size={28} className="text-muted" />
            </div>
            <p style={{ color: 'var(--text-secondary)', fontWeight: 600, marginBottom: 4 }}>هنوز کلیدی نساختهاید</p>
            <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>از فرم بالا اولین کلید API خود را بسازید</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {keys.map((k) => {
              const isRotating = rotatingId === k.id
              return (
                <div key={k.id} className={`apikeys-key-card ${!k.active ? 'apikeys-key-disabled' : ''}`}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                    <div className="flex-1 min-w-0">
                      {/* Key name + status */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                        <span style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-primary)' }}>{k.name}</span>
                        {k.active ? (
                          <span className="badge badge-positive">فعال</span>
                        ) : (
                          <span className="badge badge-danger">غیرفعال</span>
                        )}
                      </div>

                      {/* Truthful key identifier — only the real stored prefix, never a
                          fabricated "full key". There is no reveal/copy control here on
                          purpose: the full key only ever exists once, in the reveal modal. */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                        <code className="apikeys-key-value">
                          {k.prefix}{'•'.repeat(24)}
                        </code>
                      </div>

                      {/* Meta info */}
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, fontSize: 11, color: 'var(--text-muted)' }}>
                        {k.created_at && (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <Icon name="calendar" size={11} />
                            ساخت: {formatDate(k.created_at)}
                          </span>
                        )}
                        {k.last_used && (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <Icon name="clock" size={11} />
                            آخرین استفاده: {formatDate(k.last_used)}
                          </span>
                        )}
                        {k.usage_count !== undefined && (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <Icon name="chart" size={11} />
                            {faNum(k.usage_count)} درخواست
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Actions */}
                    {k.active && (
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button
                          onClick={() => rotateKey(k.id)}
                          disabled={isRotating}
                          className="btn btn-ghost btn-sm"
                          title="چرخاندن کلید (ساخت رمز جدید)"
                        >
                          {isRotating ? <span className="apikeys-spinner" /> : <Icon name="refresh" size={14} />}
                        </button>
                        <button
                          onClick={() => revokeKey(k.id)}
                          className="btn btn-ghost btn-sm apikeys-revoke-btn"
                          title="غیرفعال کردن"
                        >
                          <Icon name="trash" size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* API Docs */}
      <div className="card" style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16 }}>
          <Icon name="code" size={16} className="text-accent" />
          <h2 className="card-title">نحوه استفاده</h2>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className="apikeys-doc-num">۱</span>
              احراز هویت
            </h3>
            <pre className="apikeys-pre">
              <code>{`curl -H "Authorization: Bearer *** \\
  https://sanjabai.com/v1/chat/completions`}</code>
            </pre>
          </div>
          <div>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className="apikeys-doc-num">۲</span>
              ارسال درخواست چت
            </h3>
            <pre className="apikeys-pre">
              <code>{`{
  "model": "gpt-4o",
  "messages": [{"role": "user", "content": "سلام!"}]
}`}</code>
            </pre>
          </div>
          <div>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className="apikeys-doc-num">۳</span>
              لیست مدل‌ها
            </h3>
            <pre className="apikeys-pre">
              <code>{`curl -H "Authorization: Bearer *** \\
  https://sanjabai.com/v1/models`}</code>
            </pre>
          </div>
        </div>
      </div>

      <ApiKeyRevealModal
        open={reveal !== null}
        rawKey={reveal?.key ?? null}
        isRotation={reveal?.isRotation ?? false}
        onAcknowledge={() => setReveal(null)}
      />
    </div>
  )
}
