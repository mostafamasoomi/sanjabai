'use client'

import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '@/lib/auth'
import { toast, EmptyState, Skeleton, Tabs } from '@/components/ui'
import { Icon, type IconName } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════════════════
   Developer API Page
   ═══════════════════════════════════════════════════════════════════════════ */

type ApiKeyInfo = {
  id: number
  name: string
  prefix: string
  active: boolean
  last_used: string | null
  created_at: string | null
}

const CODE_EXAMPLES = {
  python: {
    label: 'Python',
    code: `from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://sanjabai.ir/v1"
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "شما یک دستیار فارسی هستید."},
        {"role": "user", "content": "سلام! حالت چطوره؟"}
    ]
)

print(response.choices[0].message.content)`,
    install: 'pip install openai',
  },
  curl: {
    label: 'cURL',
    code: `curl https://sanjabai.ir/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -d '{
    "model": "gpt-4o",
    "messages": [
      {"role": "system", "content": "شما یک دستیار فارسی هستید."},
      {"role": "user", "content": "سلام! حالت چطوره؟"}
    ]
  }'`,
    install: null,
  },
  javascript: {
    label: 'JavaScript',
    code: `import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "YOUR_API_KEY",
  baseURL: "https://sanjabai.ir/v1",
});

const response = await client.chat.completions.create({
  model: "gpt-4o",
  messages: [
    { role: "system", content: "شما یک دستیار فارسی هستید." },
    { role: "user", content: "سلام! حالت چطوره؟" },
  ],
});

console.log(response.choices[0].message.content);`,
    install: 'npm install openai',
  },
}

const RATE_LIMITS = [
  { plan: 'رایگان', requests: '۱۰۰ درخواست', tokens: '۱۰,۰۰۰ توکن/روز' },
  { plan: 'پایه', requests: '۱,۰۰۰ درخواست', tokens: '۱۰۰,۰۰۰ توکن/روز' },
  { plan: 'حرفه‌ای', requests: '۱۰,۰۰۰ درخواست', tokens: '۱,۰۰۰,۰۰۰ توکن/روز' },
  { plan: 'سازمانی', requests: 'نامحدود', tokens: 'نامحدود' },
]

function formatDate(s: string | null): string {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('fa-IR', { year: 'numeric', month: 'short', day: 'numeric' })
}

const ENDPOINTS = [
  {
    method: 'POST',
    path: '/v1/chat/completions',
    desc: 'ارسال درخواست چت — سازگار با OpenAI',
    body: `{
  "model": "gpt-4o",
  "messages": [
    { "role": "user", "content": "پیام شما" }
  ],
  "stream": false
}`,
  },
  {
    method: 'GET',
    path: '/v1/models',
    desc: 'دریافت لیست مدل‌های موجود',
    body: null,
  },
]

export default function DeveloperPage() {
  const { token, user, loading: authLoading } = useAuth()
  const [keys, setKeys] = useState<ApiKeyInfo[]>([])
  const [newKeyName, setNewKeyName] = useState('')
  const [newKey, setNewKey] = useState<string | null>(null)
  const [keyLoading, setKeyLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('python')
  const [copiedKey, setCopiedKey] = useState<number | null>(null)
  const [revokingId, setRevokingId] = useState<number | null>(null)

  const headers = useCallback(() => ({
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  }), [token])

  const fetchKeys = useCallback(async () => {
    if (!token) return
    try {
      const r = await fetch('/api/api-keys', { headers: headers() })
      if (r.ok) {
        const data = await r.json()
        // Backend may return array or paginated {items: [...]} format
        setKeys(Array.isArray(data) ? data : (data?.items ?? []))
      }
    } catch {}
  }, [token, headers])

  useEffect(() => {
    if (!authLoading && user) fetchKeys()
  }, [authLoading, user, fetchKeys])

  const createKey = async () => {
    if (!newKeyName.trim()) {
      toast('نام کلید را وارد کنید', 'error')
      return
    }
    setKeyLoading(true)
    try {
      const r = await fetch('/api/api-keys', {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({ name: newKeyName }),
      })
      const data = await r.json()
      if (r.ok) {
        setNewKey(data.key)
        setNewKeyName('')
        fetchKeys()
        toast('کلید جدید ساخته شد', 'success')
      } else {
        toast(data.detail || 'خطا', 'error')
      }
    } catch {
      toast('خطا در ارتباط', 'error')
    } finally {
      setKeyLoading(false)
    }
  }

  const revokeKey = async (id: number) => {
    if (!confirm('آیا از غیرفعال کردن این کلید مطمئن هستید؟')) return
    setRevokingId(id)
    try {
      const r = await fetch(`/api/api-keys/${id}`, {
        method: 'DELETE', headers: headers(),
      })
      if (r.ok) {
        toast('کلید غیرفعال شد', 'success')
        fetchKeys()
      }
    } catch {
      toast('خطا', 'error')
    } finally {
      setRevokingId(null)
    }
  }

  const copyText = (text: string) => {
    navigator.clipboard.writeText(text)
    toast('کپی شد', 'success')
  }

  if (authLoading) {
    return (
      <div style={{ padding: '24px 0' }}>
        <Skeleton height="2rem" width="300px" className="mb-6" />
        <Skeleton height="180px" className="mb-4" />
        <Skeleton height="120px" className="mb-4" />
      </div>
    )
  }

  return (
    <div style={{ padding: '24px 0' }}>
      {/* Header */}
      <div className="slide-up" style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
        <div style={{
          width: 40, height: 40, borderRadius: 12,
          background: 'linear-gradient(135deg, var(--accent), var(--accent-hover))',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon name="code" size={20} style={{ color: 'var(--text-on-accent)' }} />
        </div>
        <div>
          <h1 className="page-title">
            پلتفرم توسعه‌دهندگان
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 2 }}>
            API سازگار با OpenAI برای ادغام در اپلیکیشن‌های شما
          </p>
        </div>
      </div>

      {/* API Info Card */}
      <div className="card slide-up" style={{ marginBottom: 20, animationDelay: '0.05s' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Icon name="external" size={16} className="text-accent" />
          <h2 className="card-title">اطلاعات API</h2>
        </div>

        <div style={{
          padding: '14px 18px', borderRadius: 10,
          background: 'linear-gradient(135deg, var(--accent-bg), transparent)',
          border: '1px solid color-mix(in srgb, var(--accent) 20%, transparent)',
          marginBottom: 16,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Icon name="info" size={14} className="text-accent" />
            <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>Endpoint</span>
          </div>
          <code style={{
            display: 'block', direction: 'ltr', fontFamily: 'var(--font-mono)',
            fontSize: 15, fontWeight: 700, color: 'var(--accent)',
          }}>
            https://sanjabai.ir/v1
          </code>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '6px 0 0' }}>
            API سازگار با فرمت OpenAI — بدون تغییر در کد اصلی ادغام دهید.
          </p>
        </div>

        {/* Rate Limits */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
          <Icon name="chart" size={14} className="text-muted" />
          <h3 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>محدودیت‌های نرخی بر اساس پلن</h3>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--text-muted)', fontWeight: 600 }}>پلن</th>
                <th style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--text-muted)', fontWeight: 600 }}>درخواست</th>
                <th style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--text-muted)', fontWeight: 600 }}>توکن</th>
              </tr>
            </thead>
            <tbody>
              {RATE_LIMITS.map((r) => (
                <tr key={r.plan} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '8px 12px', color: 'var(--text-primary)', fontWeight: 600 }}>{r.plan}</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>{r.requests}</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>{r.tokens}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* API Keys Section */}
      {user && (
        <div className="card slide-up" style={{ marginBottom: 20, animationDelay: '0.1s' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Icon name="key" size={16} className="text-accent" />
            <h2 className="card-title">کلیدهای API</h2>
            {keys.length > 0 && <span className="badge badge-accent">{keys.length}</span>}
          </div>

          {/* Create new key */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <input
              className="input flex-1"
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              placeholder="نام کلید (مثلاً Development)"
              onKeyDown={(e) => e.key === 'Enter' && createKey()}
            />
            <button
              onClick={createKey}
              disabled={keyLoading}
              className="btn btn-primary"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              {keyLoading ? (
                <span style={{ width: 14, height: 14, border: '2px solid var(--text-on-accent)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
              ) : (
                <Icon name="plus" size={14} />
              )}
              ساخت کلید
            </button>
          </div>

          {/* New key display */}
          {newKey && (
            <div style={{
              padding: '14px 18px', borderRadius: 10, marginBottom: 16,
              background: 'color-mix(in srgb, var(--positive) 8%, transparent)',
              border: '1px solid color-mix(in srgb, var(--positive) 20%, transparent)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                <Icon name="check" size={14} className="text-positive" />
                <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--positive)' }}>کلید ساخته شد</span>
              </div>
              <p style={{ fontSize: 12, color: 'var(--danger)', marginBottom: 8 }}>
                ⚠️ این کلید فقط یک بار نمایش داده می‌شود. همین حالا کپی کنید.
              </p>
              <div style={{ display: 'flex', gap: 8 }}>
                <code style={{
                  flex: 1, padding: '8px 12px', borderRadius: 8,
                  background: 'var(--bg-elev)', fontSize: 13,
                  direction: 'ltr', fontFamily: 'var(--font-mono)',
                  overflow: 'auto', whiteSpace: 'nowrap',
                }}>
                  {newKey}
                </code>
                <button
                  onClick={() => copyText(newKey)}
                  className="btn btn-ghost btn-sm"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                >
                  <Icon name="copy" size={13} />
                  کپی
                </button>
              </div>
            </div>
          )}

          {/* Key list */}
          {keys.length === 0 ? (
            <EmptyState icon="key" title="هنوز کلیدی نساخته‌اید" description="اولین کلید API خود را بسازید." />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {keys.map((k) => (
                <div key={k.id} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '12px 16px', borderRadius: 10,
                  border: '1px solid var(--border)',
                  opacity: k.active ? 1 : 0.6,
                }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>{k.name}</span>
                      {k.active ? (
                        <span className="badge badge-positive" style={{ fontSize: 10 }}>فعال</span>
                      ) : (
                        <span className="badge badge-danger" style={{ fontSize: 10 }}>غیرفعال</span>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-muted)' }}>
                      <code style={{ direction: 'ltr' }}>{k.prefix}{'•'.repeat(20)}</code>
                      {k.created_at && <span>{formatDate(k.created_at)}</span>}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      onClick={() => copyText(`${k.prefix}...key_id`)}
                      className="btn btn-ghost btn-sm"
                      title="کپی"
                    >
                      <Icon name="copy" size={13} />
                    </button>
                    {k.active && (
                      <button
                        onClick={() => revokeKey(k.id)}
                        disabled={revokingId === k.id}
                        className="btn btn-ghost btn-sm text-danger"
                        title="غیرفعال کردن"
                      >
                        {revokingId === k.id ? (
                          <span style={{ width: 12, height: 12, border: '2px solid var(--danger)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.6s linear infinite', display: 'inline-block' }} />
                        ) : (
                          <Icon name="trash" size={13} />
                        )}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Code Examples */}
      <div className="card slide-up" style={{ marginBottom: 20, animationDelay: '0.15s' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Icon name="code" size={16} className="text-accent" />
          <h2 className="card-title">نمونه کد</h2>
        </div>

        <Tabs
          tabs={[
            { key: 'python', label: 'Python' },
            { key: 'curl', label: 'cURL' },
            { key: 'javascript', label: 'JavaScript' },
          ]}
          active={activeTab}
          onChange={setActiveTab}
        />

        <div style={{ marginTop: 16 }}>
          {/* Install command */}
          {CODE_EXAMPLES[activeTab as keyof typeof CODE_EXAMPLES].install && (
            <div style={{ marginBottom: 12 }}>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, display: 'block' }}>نصب وابستگی:</span>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <code style={{
                  flex: 1, padding: '8px 14px', borderRadius: 8,
                  background: 'var(--bg-surface, var(--bg-elev))',
                  fontSize: 13, direction: 'ltr', fontFamily: 'var(--font-mono)',
                  color: 'var(--text-primary)',
                }}>
                  $ {CODE_EXAMPLES[activeTab as keyof typeof CODE_EXAMPLES].install}
                </code>
                <button
                  onClick={() => copyText(CODE_EXAMPLES[activeTab as keyof typeof CODE_EXAMPLES].install!)}
                  className="btn btn-ghost btn-sm shrink-0"
                >
                  <Icon name="copy" size={13} />
                </button>
              </div>
            </div>
          )}

          {/* Code block */}
          <div className="relative">
            <pre style={{
              padding: '16px 18px', borderRadius: 10,
              background: 'var(--bg-surface, var(--bg-elev))',
              border: '1px solid var(--border)',
              fontSize: 13, direction: 'ltr', textAlign: 'left',
              fontFamily: 'var(--font-mono)', lineHeight: 1.7,
              overflow: 'auto', color: 'var(--text-primary)',
              maxHeight: 400,
            }}>
              <code>{CODE_EXAMPLES[activeTab as keyof typeof CODE_EXAMPLES].code}</code>
            </pre>
            <button
              onClick={() => copyText(CODE_EXAMPLES[activeTab as keyof typeof CODE_EXAMPLES].code)}
              className="btn btn-ghost btn-sm"
              style={{ position: 'absolute', top: 8, left: 8, display: 'inline-flex', alignItems: 'center', gap: 4 }}
            >
              <Icon name="copy" size={12} />
              کپی
            </button>
          </div>
        </div>
      </div>

      {/* Endpoint Documentation */}
      <div className="card slide-up" style={{ animationDelay: '0.2s' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Icon name="external" size={16} className="text-accent" />
          <h2 className="card-title">مستندات endpoint‌ها</h2>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {ENDPOINTS.map((ep) => (
            <div key={ep.path} style={{
              padding: '16px 18px', borderRadius: 10,
              border: '1px solid var(--border)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                <span style={{
                  padding: '3px 10px', borderRadius: 6, fontSize: 11, fontWeight: 700,
                  fontFamily: 'var(--font-mono)',
                  background: ep.method === 'POST' ? 'color-mix(in srgb, var(--positive) 10%, transparent)' : 'color-mix(in srgb, var(--info) 10%, transparent)',
                  color: ep.method === 'POST' ? 'var(--positive)' : 'var(--info)',
                }}>
                  {ep.method}
                </span>
                <code style={{ fontSize: 14, fontWeight: 600, direction: 'ltr', fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                  {ep.path}
                </code>
              </div>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '0 0 10px' }}>{ep.desc}</p>

              {ep.body && (
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>نمونه درخواست:</div>
                  <pre style={{
                    padding: '10px 14px', borderRadius: 8,
                    background: 'var(--bg-surface, var(--bg-elev))',
                    fontSize: 12, direction: 'ltr', textAlign: 'left',
                    fontFamily: 'var(--font-mono)', lineHeight: 1.6, overflow: 'auto',
                    color: 'var(--text-secondary)',
                  }}>
                    <code>{ep.body}</code>
                  </pre>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
