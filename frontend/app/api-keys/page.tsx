'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'

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
  const [newKey, setNewKey] = useState<string | null>(null)
  const [name, setName] = useState('Default')
  const [loading, setLoading] = useState(false)
  const [revealedKeys, setRevealedKeys] = useState<Set<number>>(new Set())
  const [copiedId, setCopiedId] = useState<number | null>(null)

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
      const r = await fetch('/api/api-keys', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name }),
      })
      if (r.status === 401) { router.push('/login'); return }
      const data = await r.json()
      if (r.ok) {
        setNewKey(data.key)
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

  const revokeKey = async (id: number) => {
    try {
      const r = await fetch(`/api/api-keys/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (r.status === 401) { router.push('/login'); return }
      if (r.ok) {
        toast('کلید غیرفعال شد', 'success')
        fetchKeys()
      }
    } catch {
      toast('خطا', 'error')
    }
  }

  const copyKey = (key: string, id?: number) => {
    navigator.clipboard.writeText(key)
    if (id !== undefined) {
      setCopiedId(id)
      setTimeout(() => setCopiedId(null), 2000)
    }
    toast('کلید کپی شد', 'success')
  }

  const toggleReveal = (id: number) => {
    setRevealedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const maskKey = (prefix: string, id: number) => `${prefix}${'•'.repeat(24)}${id}`

  const formatDate = (s: string | null) => {
    if (!s) return '—'
    return new Date(s).toLocaleDateString('fa-IR', { year: 'numeric', month: 'short', day: 'numeric' })
  }

  return (
    <div className="apikeys-page">
      {/* Header */}
      <div className="flex items-center gap-2.5 mb-6">
        <div className="apikeys-header-icon">
          <Icon name="key" size={20} className="text-accent" />
        </div>
        <div>
          <h1 className="text-[22px] font-bold text-primary leading-tight">کلیدهای API</h1>
          <p className="text-[13px] text-muted mt-0.5">مدیریت کلیدهای دسترسی به API</p>
        </div>
      </div>

      {/* Generate new key */}
      <div className="card apikeys-generate-card">
        <div className="flex items-center gap-2 mb-4">
          <Icon name="plus" size={16} className="text-accent" />
          <h2 className="text-[15px] font-bold text-primary">ساخت کلید جدید</h2>
        </div>
        <div className="flex gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="نام کلید (مثلاً Production)"
            className="input flex-1"
          />
 <button onClick={generateKey} disabled={loading} className="btn btn-primary inline-flex items-center gap-1.5" >
            {loading ? (
              <span className="apikeys-spinner" />
            ) : (
              <Icon name="key" size={14} />
            )}
            ساخت کلید
          </button>
        </div>
      </div>

      {/* New key display */}
      {newKey && (
        <div className="card apikeys-newkey-card">
          <div className="flex items-center gap-2 mb-2">
            <div className="apikeys-success-icon">
              <Icon name="check" size={16} className="text-positive" />
            </div>
            <h2 className="text-[15px] font-bold text-positive">کلید جدید ساخته شد</h2>
          </div>
          <p style={{ fontSize: 12, color: 'var(--danger)', marginBottom: 12, paddingRight: 28 }}>
            ⚠️ این کلید فقط یک بار نمایش داده می‌شود. همین حالا کپی کنید.
          </p>
          <div className="flex gap-2">
            <code className="apikeys-code-block flex-1">
              {newKey}
            </code>
 <button onClick={() => copyKey(newKey)} className="btn btn-secondary btn-sm apikeys-copy-btn inline-flex items-center gap-1" >
              <Icon name="copy" size={14} />
              کپی
            </button>
          </div>
        </div>
      )}

      {/* Existing keys */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-1.5">
            <Icon name="key" size={16} className="text-accent" />
            <h2 className="text-[15px] font-bold text-primary">کلیدهای شما</h2>
            {keys.length > 0 && (
              <span className="badge badge-accent">{keys.length}</span>
            )}
          </div>
        </div>

        {keys.length === 0 ? (
          <div className="apikeys-empty">
            <div className="apikeys-empty-icon">
              <Icon name="key" size={28} className="text-muted" />
            </div>
            <p style={{ color: 'var(--text-secondary)', fontWeight: 600, marginBottom: 4 }}>هنوز کلیدی نساختهاید</p>
            <p className="text-muted text-[13px]">از فرم بالا اولین کلید API خود را بسازید</p>
          </div>
        ) : (
          <div className="flex flex-col gap-2.5">
            {keys.map((k) => {
              const isRevealed = revealedKeys.has(k.id)
              const isCopied = copiedId === k.id
              return (
                <div key={k.id} className={`apikeys-key-card ${!k.active ? 'apikeys-key-disabled' : ''}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      {/* Key name + status */}
                      <div className="flex items-center gap-2 mb-2">
                        <span className="font-bold text-sm text-primary">{k.name}</span>
                        {k.active ? (
                          <span className="badge badge-positive">فعال</span>
                        ) : (
                          <span className="badge badge-danger">غیرفعال</span>
                        )}
                      </div>

                      {/* Key value with mask/reveal */}
                      <div className="flex items-center gap-1.5 mb-2">
                        <code className="apikeys-key-value">
                          {isRevealed ? `${k.prefix}...${k.id}` : maskKey(k.prefix, k.id)}
                        </code>
                        <button
                          onClick={() => toggleReveal(k.id)}
                          className="btn btn-ghost btn-sm apikeys-eye-btn"
                          title={isRevealed ? 'مخفی کردن' : 'نمایش'}
                          style={{ padding: '4px 6px' }}
                        >
                          <Icon name={isRevealed ? 'eyeOff' : 'eye'} size={14} />
                        </button>
                        <button
                          onClick={() => copyKey(`${k.prefix}...${k.id}`, k.id)}
                          className={`btn btn-ghost btn-sm apikeys-copy-btn ${isCopied ? 'apikeys-copied' : ''}`}
                          title="کپی"
                          style={{ padding: '4px 6px' }}
                        >
                          <Icon name={isCopied ? 'check' : 'copy'} size={14} />
                        </button>
                      </div>

                      {/* Meta info */}
                      <div className="flex flex-wrap gap-3 text-[11px] text-muted">
                        {k.created_at && (
                          <span className="inline-flex items-center gap-1">
                            <Icon name="calendar" size={11} />
                            ساخت: {formatDate(k.created_at)}
                          </span>
                        )}
                        {k.last_used && (
                          <span className="inline-flex items-center gap-1">
                            <Icon name="clock" size={11} />
                            آخرین استفاده: {formatDate(k.last_used)}
                          </span>
                        )}
                        {k.usage_count !== undefined && (
                          <span className="inline-flex items-center gap-1">
                            <Icon name="chart" size={11} />
                            {k.usage_count.toLocaleString('fa-IR')} درخواست
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Actions */}
                    {k.active && (
                      <button
                        onClick={() => revokeKey(k.id)}
                        className="btn btn-ghost btn-sm apikeys-revoke-btn"
                        title="غیرفعال کردن"
                      >
                        <Icon name="trash" size={14} />
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* API Docs */}
 <div className="card mt-4" >
        <div className="flex items-center gap-1.5 mb-4">
          <Icon name="code" size={16} className="text-accent" />
          <h2 className="text-[15px] font-bold text-primary">نحوه استفاده</h2>
        </div>
        <div className="flex flex-col gap-4">
          <div>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className="apikeys-doc-num">۱</span>
              احراز هویت
            </h3>
            <pre className="apikeys-pre">
              <code>{`curl -H "Authorization: Bearer *** \\
  https://multiai.ir/v1/chat/completions`}</code>
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
              لیست مدلها
            </h3>
            <pre className="apikeys-pre">
              <code>{`curl -H "Authorization: Bearer *** \\
  https://multiai.ir/v1/models`}</code>
            </pre>
          </div>
        </div>
      </div>
    </div>
  )
}
