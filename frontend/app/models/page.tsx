'use client'

import { useState, useEffect } from 'react'
import { Icon } from '@/components/ui/Icon'
import { Skeleton, EmptyState, toast } from '@/components/ui'
import {
  useCatalog,
  priceBand,
  priceBandLabel,
  PRICE_BAND_ORDER,
  contextBand,
  CONTEXT_BAND_ORDER,
  type PriceBand,
} from '@/lib/useCatalog'
import { useLang } from '@/components/LanguageToggle'
import { fmt, type Formatters } from '@/lib/i18n'
import { healthOf, isUsableModel, healthLabel } from '@/app/chat/components/modelUtils'
import type { HealthStatus, ModelCatalogItem } from '@/types/catalog'
import { modelsPageStrings } from './page.strings'

type Strings = ReturnType<typeof modelsPageStrings>

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

/* Capability tags used to map to eight per-capability colour classes, seven of
   which were never defined in the stylesheet. They are metadata, not status —
   the only coloured thing on a card should be the health badge — so they are
   uniformly neutral now. */

/** Renders a value with an optional unit, isolated in an LTR run when the
 *  unit is Latin — the bilingual equivalent of `<Num>` from lib/format,
 *  which is hard-wired to Persian digits and cannot be reused in English
 *  mode (see lib/i18n.ts's note on `<Num>` in the i18n spec). */
function BiNum({
  f,
  value,
  unit,
  compact,
}: {
  f: Formatters
  value: number | null | undefined
  unit?: string
  compact?: boolean
}) {
  const text = compact ? f.compact(value) : f.num(value)
  if (!unit) return <span className="num">{text}</span>
  if (/[A-Za-z]/.test(unit)) {
    return (
      <span className="num" dir="ltr">
        {text} {unit}
      </span>
    )
  }
  return (
    <span className="num">
      {text} <span className="num-unit">{unit}</span>
    </span>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Card
   ═══════════════════════════════════════════════════════════════════════════ */

function ModelTile({
  model,
  allModels,
  f,
  s,
  healthLabels,
  priceBandLabels,
}: {
  model: ModelCatalogItem
  allModels: ModelCatalogItem[]
  f: Formatters
  s: Strings
  healthLabels: Record<HealthStatus, string>
  priceBandLabels: Record<PriceBand, string>
}) {
  const health = healthOf(model)
  const note = s.availabilityNote[model.availability]
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
          <p className="model-tile__provider">{priceBandLabels[band]}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`model-health-badge model-health-${health.status}`}>
            <span className="model-health-dot" style={{ background: 'currentColor' }} aria-hidden />
            {healthLabels[health.status]}
          </span>
        </div>
      </div>

      <p className="model-tile__desc">{model.description || s.noDescription}</p>

      <div className="model-tile__specs">
        <div className="model-tile__spec">
          <span className="model-tile__spec-label">{s.contextWindow}</span>
          {/* A Persian/localized unit rather than a bare "token": the Latin
              word is an LTR run and the RTL paragraph was placing it
              *before* the number — "token ۱٬۰۰۰٬۰۰۰". BiNum isolates it. */}
          <span className="model-tile__spec-value">
            <BiNum f={f} value={model.contextWindow} compact unit={s.tokenUnit} />
          </span>
        </div>
        <div className="model-tile__spec">
          <span className="model-tile__spec-label">{s.latency}</span>
          <span className="model-tile__spec-value">
            {health.latencyP50Ms == null ? (
              '—'
            ) : (
              <BiNum f={f} value={health.latencyP50Ms} unit="ms" />
            )}
          </span>
        </div>
        <div className="model-tile__spec">
          <span className="model-tile__spec-label">{s.inputPerMillion}</span>
          <span className="model-tile__spec-value">
            <span className="num">{f.price(model.pricing.inputPerMillion)}</span>
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
            aria-label={s.startChatAria(model.displayName)}
          >
            <Icon name="chat" size={14} />
            {s.startChat}
          </a>
        ) : (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled
            title={s.unavailableTitle}
            aria-label={s.unavailableAria(model.displayName)}
          >
            <Icon name="chat" size={14} />
            {s.unavailable}
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
  const lang = useLang()
  const f = fmt(lang)
  const s = modelsPageStrings(lang)
  const healthLabels = healthLabel(lang)
  const priceBandLabels: Record<PriceBand, string> = {
    standard: priceBandLabel('standard', lang),
    premium: priceBandLabel('premium', lang),
  }
  const { models, loading, error } = useCatalog()
  const [filter, setFilter] = useState('all')
  const [contextFilter, setContextFilter] = useState('all')
  const [search, setSearch] = useState('')

  // Surface catalog load failures as a toast (design-system error state).
  useEffect(() => {
    if (error) toast(s.loadErrorToast, 'error')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [error])

  // Grouping/filtering used to be by `provider` (an internal routing id).
  // That field is no longer in the public catalog contract — users should
  // never see which upstream serves a model. Price band is the closest
  // honest, user-meaningful substitute: it's derived from data the item
  // already carries (pricing.inputPerMillion) and actually varies.
  const bands = PRICE_BAND_ORDER.filter((b) => models.some((m) => priceBand(m, models) === b))
  const chips = [{ key: 'all', label: s.all }, ...bands.map((b) => ({ key: b, label: priceBandLabels[b] }))]

  // Same pattern as the price chips: only offer bands that at least one
  // model on screen actually falls into, so the control never shows a
  // choice that would immediately empty the grid.
  const ctxBands = CONTEXT_BAND_ORDER.filter((b) => models.some((m) => contextBand(m.contextWindow) === b))
  const ctxChips = [
    { key: 'all', label: s.all },
    ...ctxBands.map((b) => ({ key: b, label: s.contextBand[b] })),
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
        <h1 className="page-title">{s.pageTitle}</h1>
        <p className="page-subtitle" style={{ maxWidth: '32rem' }}>
          {s.pageSubtitle}
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
        <EmptyState icon="close" title={s.loadErrorTitle} description={s.loadErrorDesc} />
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
            placeholder={s.searchPlaceholder}
            aria-label={s.searchAriaLabel}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch('')}
              className="btn btn-ghost btn-icon absolute top-1/2 -translate-y-1/2"
              style={{ insetInlineEnd: '0.25rem' }}
              aria-label={s.clearSearchAriaLabel}
            >
              <Icon name="close" size={14} />
            </button>
          )}
        </div>
        <div className="models-filters">
          <span className="models-filter-label">{s.priceFilterLabel}</span>
          {chips.map((c) => (
            <button
              key={c.key}
              onClick={() => setFilter(c.key)}
              className={`aurora-chip ${filter === c.key ? 'active' : ''}`}
              aria-pressed={filter === c.key}
            >
              {c.label}
            </button>
          ))}
        </div>
        <div className="models-filters">
          <span className="models-filter-label">{s.contextFilterLabel}</span>
          {ctxChips.map((c) => (
            <button
              key={c.key}
              onClick={() => setContextFilter(c.key)}
              className={`aurora-chip ${contextFilter === c.key ? 'active' : ''}`}
              aria-pressed={contextFilter === c.key}
            >
              {c.label}
            </button>
          ))}
        </div>
        {hasActiveFilters && (
          <button type="button" onClick={clearFilters} className="btn btn-ghost btn-sm">
            <Icon name="close" size={12} />
            {s.clearFilters}
          </button>
        )}
        <p className="models-count">
          {hasActiveFilters
            ? s.resultCountOfTotal(f.num(filtered.length), f.num(models.length))
            : s.resultCount(f.num(filtered.length))}
        </p>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon="search"
          title={s.emptyTitle}
          description={hasActiveFilters ? s.emptyDescFiltered : s.emptyDescUnfiltered}
        >
          {hasActiveFilters && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={clearFilters}>
              {s.clearFilters}
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
              f={f}
              s={s}
              healthLabels={healthLabels}
              priceBandLabels={priceBandLabels}
            />
          ))}
        </div>
      )}
    </div>
  )
}
