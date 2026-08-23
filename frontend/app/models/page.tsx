'use client'

import { useState, useEffect } from 'react'
import { Icon } from '@/components/ui/Icon'
import { Skeleton, EmptyState, toast } from '@/components/ui'
import {
  useCatalog,
  priceBand,
  PRICE_BAND_LABEL,
  PRICE_BAND_ORDER,
  contextBand,
  CONTEXT_BAND_LABEL,
  CONTEXT_BAND_ORDER,
} from '@/lib/useCatalog'
import { Num, faNum } from '@/lib/format'
import { HEALTH_LABEL, healthOf, isUsableModel } from '@/app/chat/components/modelUtils'
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

function ModelTile({ model, allModels }: { model: ModelCatalogItem; allModels: ModelCatalogItem[] }) {
  const health = healthOf(model)
  const note = AVAILABILITY_NOTE[model.availability]
  const band = priceBand(model, allModels)
  // Same usability check ModelPicker filters chat model selection by
  // (status !== 'down') — this link must not offer a chat that the picker
  // itself would refuse to start.
  const usable = isUsableModel(model)

  return (
    <article className="model-tile">
      <div className="model-tile__head">
        <div style={{ minWidth: 0 }}>
          {/* h2, not h3: the page h1 is the only level above it, and an
              h1 → h3 jump broke the outline for heading navigation. */}
          <h2 className="model-tile__name" dir="ltr">{model.displayName}</h2>
          <p className="model-tile__provider">{PRICE_BAND_LABEL[band]}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
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
            The model name lives in the accessible name instead.

            Only linked when the model is usable: ModelPicker (the chat
            page's own model selector) filters out anything with
            health.status === 'down', so a link into /chat for a down model
            would land the user on a picker that refuses the very model
            this button promised. */}
        {usable ? (
          <a
            href={`/chat?model=${encodeURIComponent(model.id)}`}
            className="btn btn-secondary btn-sm"
            aria-label={`شروع چت با ${model.displayName}`}
          >
            <Icon name="chat" size={14} />
            شروع چت
          </a>
        ) : (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled
            title="این مدل در حال حاضر در دسترس نیست"
            aria-label={`${model.displayName} در حال حاضر در دسترس نیست`}
          >
            <Icon name="chat" size={14} />
            در دسترس نیست
          </button>
        )}
      </div>
    </article>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Page
   ═══════════════════════════════════════════════════════════════════════════ */

export default function ModelsPage() {
  const { models, loading, error } = useCatalog()
  const [filter, setFilter] = useState('all')
  const [contextFilter, setContextFilter] = useState('all')
  const [search, setSearch] = useState('')

  // Surface catalog load failures as a toast (design-system error state).
  useEffect(() => {
    if (error) toast('خطا در دریافت فهرست مدل‌ها', 'error')
  }, [error])

  // Grouping/filtering used to be by `provider` (an internal routing id).
  // That field is no longer in the public catalog contract — users should
  // never see which upstream serves a model. Price band is the closest
  // honest, user-meaningful substitute: it's derived from data the item
  // already carries (pricing.inputPerMillion) and actually varies.
  const bands = PRICE_BAND_ORDER.filter((b) => models.some((m) => priceBand(m, models) === b))
  const chips = [{ key: 'all', label: 'همه' }, ...bands.map((b) => ({ key: b, label: PRICE_BAND_LABEL[b] }))]

  // Same pattern as the price chips: only offer bands that at least one
  // model on screen actually falls into, so the control never shows a
  // choice that would immediately empty the grid.
  const ctxBands = CONTEXT_BAND_ORDER.filter((b) => models.some((m) => contextBand(m.contextWindow) === b))
  const ctxChips = [
    { key: 'all', label: 'همه' },
    ...ctxBands.map((b) => ({ key: b, label: CONTEXT_BAND_LABEL[b] })),
  ]

  const searchQuery = search.trim().toLowerCase()
  const filtered = models
    .filter((m) => filter === 'all' || priceBand(m, models) === filter)
    .filter((m) => contextFilter === 'all' || contextBand(m.contextWindow) === contextFilter)
    .filter(
      (m) =>
        !searchQuery ||
        m.displayName.toLowerCase().includes(searchQuery) ||
        (m.description ?? '').toLowerCase().includes(searchQuery),
    )

  const hasActiveFilters = filter !== 'all' || contextFilter !== 'all' || searchQuery.length > 0
  const clearFilters = () => {
    setFilter('all')
    setContextFilter('all')
    setSearch('')
  }

  // "تست همه مدل‌ها" used to live here, calling the admin-only
  // /api/admin/test-models endpoint. It is now admin_required-gated
  // (backend/content.py:1092) — every ordinary user got a silent no-op
  // (the fetch was never checked for res.ok) while also being able to
  // trigger one real upstream call per model. Removed rather than
  // admin-gated: this is a public page, and the action never belonged on
  // it — model testing is an admin-panel concern.
  const header = (
    <header className="models-header">
      <div>
        <h1 className="page-title">مدل‌های هوش مصنوعی</h1>
        <p className="page-subtitle" style={{ maxWidth: '32rem' }}>
          همه مدل‌ها از یک پنل — وضعیت هر مدل به‌صورت زنده اندازه‌گیری می‌شود.
        </p>
      </div>
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
            <div key={i} className="model-tile" style={{ animationDelay: `${i * 100}ms` }}>
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
      <div className="models-toolbar">
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
            placeholder="جستجو در نام یا توضیح مدل..."
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
          <span className="models-filter-label">قیمت:</span>
          {chips.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`aurora-chip ${filter === f.key ? 'active' : ''}`}
              aria-pressed={filter === f.key}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="models-filters">
          <span className="models-filter-label">پنجره‌ی متن:</span>
          {ctxChips.map((f) => (
            <button
              key={f.key}
              onClick={() => setContextFilter(f.key)}
              className={`aurora-chip ${contextFilter === f.key ? 'active' : ''}`}
              aria-pressed={contextFilter === f.key}
            >
              {f.label}
            </button>
          ))}
        </div>
        {hasActiveFilters && (
          <button type="button" onClick={clearFilters} className="btn btn-ghost btn-sm">
            <Icon name="close" size={12} />
            پاک کردن فیلترها
          </button>
        )}
        <p className="models-count">{faNum(filtered.length)} مدل{hasActiveFilters ? ` از ${faNum(models.length)}` : ''}</p>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon="search"
          title="مدلی یافت نشد"
          description={
            hasActiveFilters
              ? 'برای فیلترها و عبارت جستجوی انتخابی شما مدلی موجود نیست.'
              : 'در حال حاضر مدلی در فهرست موجود نیست.'
          }
        >
          {hasActiveFilters && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={clearFilters}>
              پاک کردن فیلترها
            </button>
          )}
        </EmptyState>
      ) : (
        <div className="models-grid">
          {filtered.map((m) => (
            <ModelTile
              key={m.id}
              model={m}
              allModels={models}
            />
          ))}
        </div>
      )}
    </div>
  )
}
