'use client'

import { useState, useEffect } from 'react'
import { Icon } from '@/components/ui/Icon'
import { Skeleton, EmptyState, toast } from '@/components/ui'
import { useAuth } from '@/lib/auth'
import { useCatalog } from '@/lib/useCatalog'
import { Num, faNum } from '@/lib/format'
import { HEALTH_LABEL, healthOf } from '@/app/chat/components/modelUtils'
import type { Availability, ModelCatalogItem } from '@/types/catalog'

/* ═══════════════════════════════════════════════════════════════════════════
   Model catalog.

   Every card used to show a static "در دسترس" read off `availability`, which
   is an editorial flag — whether we intend to offer the model at all. The
   catalog response also carries a measured `health` block (status, success
   rate, latency), which /status already renders and this page ignored: a user
   picking a model here got no signal that it was degraded. Health is now the
   badge; `availability` only surfaces when it says something health does not
   (maintenance, withdrawn).
   ═══════════════════════════════════════════════════════════════════════════ */

/** Editorial availability, shown only when it is not the ordinary case. */
const AVAILABILITY_NOTE: Partial<Record<Availability, string>> = {
  maintenance: 'در حال نگهداری',
  disabled: 'غیرفعال',
}

/* Capability tags used to map to eight per-capability colour classes, seven of
   which were never defined in the stylesheet. They are metadata, not status —
   the only coloured thing on a card should be the health badge — so they are
   uniformly neutral now. */

/* ═══════════════════════════════════════════════════════════════════════════
   Card
   ═══════════════════════════════════════════════════════════════════════════ */

function ModelTile({ model, probe, index = 0 }: { model: ModelCatalogItem; probe?: { ok: boolean }; index?: number }) {
  const health = healthOf(model)
  const note = AVAILABILITY_NOTE[model.availability]

  return (
    <article className="model-tile slide-up" style={{ animationDelay: `${Math.min(index, 10) * 0.03}s` }}>
      <div className="model-tile__head">
        <div style={{ minWidth: 0 }}>
          {/* h2, not h3: the page h1 is the only level above it, and an
              h1 → h3 jump broke the outline for heading navigation. */}
          <h2 className="model-tile__name" dir="ltr">{model.displayName}</h2>
          <p className="model-tile__provider" dir="ltr">{model.provider}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {probe && <span className="text-xs">{probe.ok ? '✅' : '❌'}</span>}
          <span className={`model-health-badge model-health-${health.status}`}>
            <span className="model-health-dot" style={{ background: 'currentColor' }} aria-hidden />
            {HEALTH_LABEL[health.status]}
          </span>
        </div>
      </div>

      <p className="model-tile__desc">{model.description || 'بدون توضیح'}</p>

      <div className="model-tile__specs">
        <div className="model-tile__spec">
          <span className="model-tile__spec-label">پنجره‌ی متن</span>
          {/* Persian unit rather than a bare "token": the Latin word is an
              LTR run and the RTL paragraph was placing it *before* the
              number — "token ۱٬۰۰۰٬۰۰۰". */}
          <span className="model-tile__spec-value">
            <Num value={model.contextWindow} compact unit="توکن" />
          </span>
        </div>
        <div className="model-tile__spec">
          <span className="model-tile__spec-label">تأخیر میانه</span>
          <span className="model-tile__spec-value">
            {health.latencyP50Ms == null ? (
              '—'
            ) : (
              <Num value={health.latencyP50Ms} unit="ms" />
            )}
          </span>
        </div>
        <div className="model-tile__spec">
          <span className="model-tile__spec-label">ورودی / میلیون</span>
          <span className="model-tile__spec-value">
            <Num value={model.pricing.inputPerMillion} unit="تومان" />
          </span>
        </div>
      </div>

      {model.capabilities.length > 0 && (
        <div className="model-tile__caps">
          {model.capabilities.map((c) => (
            <span key={c} className="aurora-cap-tag" dir="ltr">
              {c}
            </span>
          ))}
        </div>
      )}

      <div className="model-tile__foot">
        {note ? <span className="model-tile__note">{note}</span> : <span />}
        {/* Secondary, not primary: on a page whose job is comparison, three
            saturated bars all reading "شروع چت با <title>" were the loudest
            thing on screen and repeated information already in the heading.
            The model name lives in the accessible name instead. */}
        <a
          href={`/chat?model=${encodeURIComponent(model.id)}`}
          className="btn btn-secondary btn-sm"
          aria-label={`شروع چت با ${model.displayName}`}
        >
          <Icon name="chat" size={14} />
          شروع چت
        </a>
      </div>
    </article>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Page
   ═══════════════════════════════════════════════════════════════════════════ */

export default function ModelsPage() {
  const { models, loading, error } = useCatalog()
  const { token } = useAuth()
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [testing, setTesting] = useState(false)
  const [testResults, setTestResults] = useState<{ id: string; ok: boolean }[]>([])

  const handleTestModels = async () => {
    setTesting(true)
    setTestResults([])
    try {
      const t = token || localStorage.getItem('sanjabai_auth_token')
      const r = await fetch('/api/admin/test-models', { headers: { Authorization: `Bearer ${t}` } })
      const d = await r.json()
      setTestResults(d.results || [])
    } catch {
      toast('خطا در تست مدل‌ها', 'error')
    } finally {
      setTesting(false)
    }
  }

  // Surface catalog load failures as a toast (design-system error state).
  useEffect(() => {
    if (error) toast('خطا در دریافت فهرست مدل‌ها', 'error')
  }, [error])

  const providers = Array.from(new Set(models.map((m) => m.provider)))
  const chips = [{ key: 'all', label: 'همه' }, ...providers.map((p) => ({ key: p, label: p }))]
  const filtered = (filter === 'all' ? models : models.filter((m) => m.provider === filter)).filter(
    (m) =>
      !search ||
      m.displayName.toLowerCase().includes(search.toLowerCase()) ||
      m.provider.toLowerCase().includes(search.toLowerCase()),
  )

  const header = (
    <header className="models-header slide-up">
      <div>
        <h1 className="page-title">مدل‌های هوش مصنوعی</h1>
        <p className="page-subtitle" style={{ maxWidth: '32rem' }}>
          همه مدل‌ها از یک پنل — وضعیت هر مدل به‌صورت زنده اندازه‌گیری می‌شود.
        </p>
      </div>
      <button className="btn btn-sm btn-secondary" onClick={handleTestModels} disabled={testing}>
        <Icon name="refresh" size={14} />
        {testing ? 'در حال تست...' : 'تست همه مدل‌ها'}
      </button>
    </header>
  )

  if (loading) {
    return (
      <div className="models-page">
        {header}
        <div className="models-toolbar">
          <div className="models-search">
            <Skeleton className="h-10 rounded-lg" />
          </div>
        </div>
        <div className="models-grid">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="model-tile slide-up" style={{ animationDelay: `${i * 100}ms` }}>
              <div className="model-tile__head">
                <div className="space-y-2 w-full">
                  <Skeleton className="w-1/2" height="1.1rem" />
                  <Skeleton className="w-1/3" height="0.75rem" />
                </div>
                <Skeleton className="w-16" height="1.25rem" />
              </div>
              <Skeleton className="w-full" height="2.5rem" />
              <Skeleton className="w-full" height="2rem" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="models-page">
        {header}
        <EmptyState
          icon="close"
          title="خطا در بارگذاری"
          description="در حال حاضر امکان دریافت فهرست مدل‌ها وجود ندارد. لطفاً بعداً تلاش کنید."
        />
      </div>
    )
  }

  return (
    <div className="models-page">
      {header}

      {/* Search sized to its content, chips take the rest of the row, and the
          result count sits at the end of the same row instead of on a line of
          its own. */}
      <div className="models-toolbar slide-up" style={{ animationDelay: '0.05s' }}>
        <div className="models-search">
          <Icon
            name="search"
            size={16}
            className="absolute top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
            style={{ insetInlineStart: '0.75rem' }}
          />
          <input
            type="text"
            className="input"
            style={{ paddingInlineStart: '2.25rem' }}
            placeholder="جستجوی مدل..."
            aria-label="جستجوی مدل"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch('')}
              className="btn btn-ghost btn-icon absolute top-1/2 -translate-y-1/2"
              style={{ insetInlineEnd: '0.25rem' }}
              aria-label="پاک کردن جستجو"
            >
              <Icon name="close" size={14} />
            </button>
          )}
        </div>
        <div className="models-filters">
          {chips.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`aurora-chip ${filter === f.key ? 'active' : ''}`}
              aria-pressed={filter === f.key}
              dir={f.key === 'all' ? undefined : 'ltr'}
            >
              {f.label}
            </button>
          ))}
        </div>
        <p className="models-count">{faNum(filtered.length)} مدل</p>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon="search"
          title="مدلی یافت نشد"
          description="برای فیلتر انتخابی شما مدلی موجود نیست."
        />
      ) : (
        <div className="models-grid">
          {filtered.map((m, idx) => (
            <ModelTile
              key={m.id}
              model={m}
              index={idx}
              probe={testResults.find((r) => r.id === m.id || r.id === m.providerModelId)}
            />
          ))}
        </div>
      )}

      {testResults.length > 0 && (
        <section className="card slide-up">
          <h2 className="card-title" style={{ marginBottom: 'var(--space-3)' }}>
            نتایج تست مدل‌ها — {faNum(testResults.filter((r) => r.ok).length)} از{' '}
            {faNum(testResults.length)} فعال
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            {testResults.map((r) => (
              <div
                key={r.id}
                className={`flex items-center gap-2 p-2 rounded ${r.ok ? 'bg-[var(--positive)]/10' : 'bg-[var(--danger)]/10'}`}
              >
                <span>{r.ok ? '✅' : '❌'}</span>
                <span className="truncate" dir="ltr">{r.id}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
