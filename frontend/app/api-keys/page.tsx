'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'

type ApiKeyInfo = {
  id: number
  name: string
  prefix: string
  active: boolean
  last_used: string | null
  created_at: string | null
}

export default function ApiKeysPage() {
  const { user } = useAuth()
  const [keys, setKeys] = useState<ApiKeyInfo[]>([])
  const [newKey, setNewKey] = useState<string | null>(null)
  const [name, setName] = useState('Default')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (user) fetchKeys()
  }, [user])

  const fetchKeys = async () => {
    try {
      const token = localStorage.getItem('token')
      const r = await fetch('/api/api-keys', { headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) setKeys(await r.json())
    } catch {}
  }

  const generateKey = async () => {
    setLoading(true)
    try {
      const token = localStorage.getItem('token')
      const r = await fetch('/api/api-keys', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name }),
      })
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
      const token = localStorage.getItem('token')
      const r = await fetch(`/api/api-keys/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (r.ok) {
        toast('کلید غیرفعال شد', 'success')
        fetchKeys()
      }
    } catch {
      toast('خطا', 'error')
    }
  }

  const copyKey = (key: string) => {
    navigator.clipboard.writeText(key)
    toast('کلید کپی شد', 'success')
  }

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold">کلیدهای API</h1>

      <div className="card">
        <h2 className="text-lg font-bold mb-4">ساخت کلید جدید</h2>
        <div className="flex gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="نام کلید (مثلاً Production)"
            className="input flex-1"
          />
          <button onClick={generateKey} disabled={loading} className="btn btn-primary">
            {loading ? '⏳' : '🔑 ساخت کلید'}
          </button>
        </div>
      </div>

      {/* New key display */}
      {newKey && (
        <div className="card border-2 border-[var(--success)]/30 bg-[var(--success)]/5">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-2xl">✅</span>
            <h2 className="text-lg font-bold text-[var(--success)]">کلید جدید ساخته شد</h2>
          </div>
          <p className="text-sm text-[var(--danger)] mb-3">
            ⚠️ این کلید فقط یک بار نمایش داده می‌شود. همین حالا کپی کنید.
          </p>
          <div className="flex gap-2">
            <code className="flex-1 p-3 rounded-lg bg-[var(--bg)] border border-[var(--border)] text-sm font-mono break-all">
              {newKey}
            </code>
            <button onClick={() => copyKey(newKey)} className="btn btn-secondary btn-sm">
              📋 کپی
            </button>
          </div>
        </div>
      )}

      {/* Existing keys */}
      <div className="card">
        <h2 className="text-lg font-bold mb-4">کلیدهای شما</h2>
        {keys.length === 0 ? (
          <p className="text-sm text-[var(--text-dim)] py-4 text-center">هنوز کلیدی نساخته‌اید</p>
        ) : (
          <div className="space-y-2">
            {keys.map((k) => (
              <div key={k.id} className="flex items-center justify-between p-3 rounded-lg bg-[var(--bg-hover)]">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm">{k.name}</span>
                    {k.active ? (
                      <span className="badge text-[var(--success)] text-xs">فعال</span>
                    ) : (
                      <span className="badge text-[var(--danger)] text-xs">غیرفعال</span>
                    )}
                  </div>
                  <div className="text-xs text-[var(--text-muted)] mt-1">
                    <code>{k.prefix}...{k.id}</code>
                    {k.last_used && (
                      <span className="mr-2">آخرین استفاده: {new Date(k.last_used).toLocaleDateString('fa-IR')}</span>
                    )}
                  </div>
                </div>
                {k.active && (
                  <button onClick={() => revokeKey(k.id)} className="btn btn-ghost btn-sm text-[var(--danger)]">
                    🗑️
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* API Docs */}
      <div className="card">
        <h2 className="text-lg font-bold mb-4">نحوه استفاده</h2>
        <div className="space-y-4">
          <div>
            <h3 className="text-sm font-semibold mb-2">🔹 احراز هویت</h3>
            <pre className="p-3 rounded-lg bg-[var(--bg)] border border-[var(--border)] text-xs overflow-x-auto">
              <code>{`curl -H "Authorization: Bearer sk-YOUR_API_KEY" \\
  https://multiai.ir/v1/chat/completions`}</code>
            </pre>
          </div>
          <div>
            <h3 className="text-sm font-semibold mb-2">🔹 ارسال درخواست چت</h3>
            <pre className="p-3 rounded-lg bg-[var(--bg)] border border-[var(--border)] text-xs overflow-x-auto">
              <code>{`{
  "model": "gpt-4o",
  "messages": [{"role": "user", "content": "سلام!"}]
}`}</code>
            </pre>
          </div>
          <div>
            <h3 className="text-sm font-semibold mb-2">🔹 لیست مدل‌ها</h3>
            <pre className="p-3 rounded-lg bg-[var(--bg)] border border-[var(--border)] text-xs overflow-x-auto">
              <code>{`curl -H "Authorization: Bearer sk-YOUR_API_KEY" \\
  https://multiai.ir/v1/models`}</code>
            </pre>
          </div>
        </div>
      </div>
    </div>
  )
}