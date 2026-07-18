'use client'

import { useState, useEffect } from 'react'
import { Icon } from '@/components/ui/Icon'
import { Skeleton, EmptyState, toast } from '@/components/ui'
import { useAuth } from '@/lib/auth'
import { useCatalog } from '@/lib/useCatalog'
import type { Availability } from '@/types/catalog'

const STATUS: Record<Availability, { label: string; color: string }> = {
  available: { label: 'در دسترس', color: 'badge-positive' },
  degraded: { label: 'محدود', color: 'badge-warning' },
  maintenance: { label: 'در حال نگهداری', color: 'badge-warning' },
  disabled: { label: 'غیرفعال', color: 'badge-danger' },
}

/* Capability color map */
const CAP_COLORS: Record<string, string> = {
  chat: 'aurora-cap-blue',
  code: 'aurora-cap-purple',
  vision: 'aurora-cap-cyan',
  reasoning: 'aurora-cap-amber',
  function_calling: 'aurora-cap-green',
  embedding: 'aurora-cap-pink',
  image: 'aurora-cap-rose',
  audio: 'aurora-cap-teal',
  default: 'aurora-cap-default',
}

function getCapColor(cap: string): string {
  const key = cap.toLowerCase().replace(/[\s-]/g, '_')
  return CAP_COLORS[key] || CAP_COLORS.default
}

export default function ModelsPage() {
  const [testing, setTesting] = useState(false);
  const [testResults, setTestResults] = useState<any[]>([]);

  const handleTestModels = async () => {
    setTesting(true); setTestResults([]);
    try {
      const t = token || localStorage.getItem('multiai_auth_token');
      const r = await fetch("/api/admin/test-models", { headers: { Authorization: `Bearer ${t}` } });
      const d = await r.json();
      setTestResults(d.results || []);
    } catch { toast("خطا در تست مدلها", "error"); }
    finally { setTesting(false); }
  };
    const { models, loading, error } = useCatalog()
  const { token } = useAuth()
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')

  // Surface catalog load failures as a toast (design-system error state).
  useEffect(() => {
    if (error) toast('خطا در دریافت فهرست مدلها', 'error')
  }, [error])

  const providers = Array.from(new Set(models.map((m) => m.provider)))
  const chips = [
    { key: 'all', label: 'همه' },
    ...providers.map((p) => ({ key: p, label: p })),
  ]
  const filtered = (filter === 'all' ? models : models.filter((m) => m.provider === filter))
    .filter((m) => !search || m.displayName.toLowerCase().includes(search.toLowerCase()) || m.provider.toLowerCase().includes(search.toLowerCase()))

  if (loading) {
    return (
      <div className="py-6">
        <div className="mb-8">
          <h1 className="aurora-section-title text-2xl font-bold mb-2">مدلهای هوش مصنوعی</h1>
          <p className="text-[var(--text-secondary)]">در حال بارگذاری فهرست مدلها...</p>
        </div>
        {/* Search bar skeleton */}
        <div className="aurora-search-bar mb-6">
          <Skeleton className="w-full h-10 rounded-lg" />
        </div>
        <div className="aurora-model-grid grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="aurora-skeleton-card card" style={{ animationDelay: `${i * 100}ms` }}>
              <div className="flex items-start justify-between mb-3">
                <div className="space-y-2 w-full">
                  <Skeleton className="w-1/2" height="1.1rem" />
                  <Skeleton className="w-1/3" height="0.75rem" />
                </div>
                <Skeleton className="w-16" height="1.25rem" />
              </div>
              <Skeleton className="w-full mb-3" height="2.5rem" />
              <div className="flex gap-2 mb-4">
                <Skeleton className="w-14" height="1.25rem" />
                <Skeleton className="w-14" height="1.25rem" />
                <Skeleton className="w-14" height="1.25rem" />
              </div>
              <Skeleton className="w-full" height="2rem" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="py-6">
        <div className="mb-8">
          <h1 className="text-2xl font-bold mb-2">مدلهای هوش مصنوعی</h1>
        </div>
        <EmptyState
          icon="close"
          title="خطا در بارگذاری"
          description="در حال حاضر امکان دریافت فهرست مدلها وجود ندارد. لطفاً بعداً تلاش کنید."
        />
      </div>
    )
  }

  return (
    <div className="py-6">
      <div className="mb-8 flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="aurora-section-title text-2xl font-bold mb-2">مدلهای هوش مصنوعی</h1>
          <p className="text-[var(--text-secondary)] leading-relaxed" style={{maxWidth: '480px'}}>همه مدلها از یک پنل — بهترین مدل را برای نیاز خود انتخاب کنید</p>
        </div>
        <button className="btn btn-sm btn-secondary" onClick={handleTestModels} disabled={testing}>
          {testing ? '⏳ در حال تست...' : '🧪 تست همه مدلها'}
        </button>
      </div>

      {/* Search + Filter bar */}
      <div className="aurora-search-bar mb-6 flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Icon name="search" size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
          <input
            type="text"
            className="input aurora-search-input pr-9"
            placeholder="جستجوی مدل..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch('')}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
              aria-label="پاک کردن"
            >
              <Icon name="close" size={14} />
            </button>
          )}
        </div>
        <div className="aurora-filter-chips flex gap-2 overflow-x-auto pb-1">
          {chips.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`aurora-chip btn btn-sm whitespace-nowrap ${filter === f.key ? 'btn-primary' : 'btn-ghost'}`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Results count */}
      <p className="text-xs text-[var(--text-muted)] mb-4">{filtered.length} مدل</p>

      {filtered.length === 0 ? (
        <EmptyState
          icon="search"
          title="مدلی یافت نشد"
          description="برای فیلتر انتخابی شما مدلی موجود نیست."
        />
      ) : (
        <div className="aurora-model-grid grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((m, i) => (
            <div key={m.id} className="aurora-model-card card card-interactive" style={{ animationDelay: `${i * 50}ms` }}>
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-bold text-base">{m.displayName}</h3>
                  <p className="text-xs text-[var(--text-muted)]">{m.provider}</p>
                </div>
                <div className="flex items-center gap-2">
                  {testResults.length > 0 && (() => {
                    const tr = testResults.find((r:any) => r.id === m.id || r.id === m.providerModelId)
                    return tr ? <span className="text-xs">{tr.ok ? '✅' : '❌'}</span> : null
                  })()}
                  <span className={`badge ${STATUS[m.availability]?.color || 'badge-accent'}`}>
                    {STATUS[m.availability]?.label || m.availability}
                  </span>
                </div>
              </div>

              <p className="text-sm text-[var(--text-secondary)] mb-3 leading-relaxed line-clamp-2">
                {m.description || '—'}
              </p>

              <div className="flex items-center gap-4 text-xs text-[var(--text-muted)] mb-3">
                <span className="flex items-center gap-1">
                  <Icon name="models" size={12} />
                  {m.contextWindow.toLocaleString()} token
                </span>
              </div>

              <div className="aurora-cap-tags flex flex-wrap gap-1.5 mb-4">
                {m.capabilities.map((c) => (
                  <span key={c} className={`aurora-cap-tag ${getCapColor(c)}`}>
                    {c}
                  </span>
                ))}
              </div>

              <a href={`/chat?model=${encodeURIComponent(m.id)}`} className="btn btn-primary btn-sm w-full aurora-model-cta">
                <Icon name="chat" size={14} />
                شروع چت با {m.displayName}
              </a>
            </div>
          ))}
        </div>
      )}

      {/* Test results */}
      {testResults.length > 0 && (
        <div className="mt-6 card p-4">
          <h3 className="text-sm font-bold mb-3">نتایج تست مدلها ({testResults.filter((r:any)=>r.ok).length}/{testResults.length} فعال)</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            {testResults.map((r:any) => (
              <div key={r.id} className={`flex items-center gap-2 p-2 rounded ${r.ok ? 'bg-[var(--positive)]/10' : 'bg-[var(--danger)]/10'}`}>
                <span>{r.ok ? '✅' : '❌'}</span>
                <span className="truncate" dir="ltr">{r.id}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
