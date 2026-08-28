'use client'

import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { type HealthStatus, type ModelCatalogItem } from '@/types/catalog'
import { Icon } from '@/components/ui/Icon'
import { useLang, type Lang } from '@/components/LanguageToggle'
import { fmt, dirFor } from '@/lib/i18n'
import { priceBand, priceBandLabel, PRICE_BAND_ORDER, type PriceBand } from '@/lib/useCatalog'
import { useKeepInViewport } from '../hooks/useKeepInViewport'
import {
  healthOf,
  isUsableModel,
  healthLabel,
  HEALTH_TONE,
  getModelIcon,
  formatPriceIRT,
  formatContextWindow,
  isRecommendedModel,
} from './modelUtils'
import { modelPickerStrings } from './ModelPicker.strings'

const STORAGE_KEY = 'sanjabai_selected_model'

type Props = {
  models: ModelCatalogItem[]
  selected: ModelCatalogItem | null
  onSelect: (m: ModelCatalogItem) => void
  loading: boolean
  disabled?: boolean
  smartModeActive?: boolean
}

function normalize(str: string): string {
  return (str || '').toLowerCase().trim()
}

function uniqueById(list: ModelCatalogItem[]): ModelCatalogItem[] {
  const seen = new Set<string>()
  const out: ModelCatalogItem[] = []
  for (const m of list) {
    if (!seen.has(m.id)) {
      seen.add(m.id)
      out.push(m)
    }
  }
  return out
}

export default function ModelPicker({ models, selected, onSelect, loading, disabled, smartModeActive }: Props) {
  const lang = useLang()
  const s = modelPickerStrings(lang)
  const f = fmt(lang)
  const health = healthLabel(lang)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [focusedIdx, setFocusedIdx] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Persist selection
  useEffect(() => {
    if (selected?.id) {
      try {
        localStorage.setItem(STORAGE_KEY, selected.id)
      } catch {}
    }
  }, [selected?.id])

  // Restore from localStorage once when models arrive and no selection
  useEffect(() => {
    if (selected || models.length === 0) return
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (!stored) return
      const found = models.find(m => m.id === stored)
      if (found) onSelect(found)
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [models])

  // Focus search on open
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50)
      // set initial focused index to selected
      const flat = getFlatFiltered()
      const selIdx = selected ? flat.findIndex(m => m.id === selected.id) : 0
      setFocusedIdx(selIdx >= 0 ? selIdx : 0)
    } else {
      setQuery('')
      // return focus to trigger for a11y
      triggerRef.current?.focus()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // Click outside to close
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      const target = e.target as Node
      if (rootRef.current && !rootRef.current.contains(target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // Escape to close + prevent body scroll on mobile modal
  useEffect(() => {
    if (!open) return
    const prevOverflow = document.body.style.overflow
    // lock scroll on small screens
    if (window.innerWidth < 640) document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prevOverflow }
  }, [open])

  // `.model-picker-dropdown` (globals.css) anchors via `inset-inline-start: 0`
  // against ITS OWN containing block (`.model-picker-root`, sized to the
  // trigger) -- not the viewport. On narrow/mid screens where the trigger
  // isn't flush against a screen edge the dropdown's far edge lands
  // off-screen (measured: up to -130px past the left edge on a 768px
  // viewport). Same fix as SmartModePopover, shared via the hook so the two
  // don't diverge.
  useKeepInViewport(dropdownRef, open)

  const filtered = useMemo(() => {
    // Models the backend has measured as down are dropped before anything else
    // — offering one guarantees the user an error. `unknown` and `degraded`
    // stay: unknown just means unexercised, and degraded still answers.
    const usable = models.filter(isUsableModel)
    const q = normalize(query)
    if (!q) return usable
    return usable.filter(m => {
      const hay = [
        m.displayName,
        m.id,
        m.providerModelId,
        (m.description || ''),
        (m.capabilities || []).join(' '),
        (m.recommendedFor || []).join(' '),
      ].join(' ').toLowerCase()
      return hay.includes(q)
    })
  }, [models, query])

  const recommended = useMemo(() => {
    const list = filtered.filter(isRecommendedModel)
    // recommendedFor includes common first
    return uniqueById(list).slice(0, 12)
  }, [filtered])

  // Used to group by `provider` (an internal routing id like "bynara" or
  // "freellmapi-s2") — that leaked which upstream serves a model, which only
  // admins should see. Grouping now uses a price band derived from
  // pricing.inputPerMillion instead: it's honest, user-meaningful, and (like
  // provider) actually varies across the catalog.
  const groupedByBand = useMemo(() => {
    const map = new Map<PriceBand, ModelCatalogItem[]>()
    for (const m of filtered) {
      const key = priceBand(m, filtered)
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(m)
    }
    return PRICE_BAND_ORDER
      .filter(band => map.has(band))
      .map(band => [band, map.get(band)!] as [PriceBand, ModelCatalogItem[]])
  }, [filtered])

  // flat list in display order for keyboard nav
  const getFlatFiltered = useCallback(() => {
    const seen = new Set<string>()
    const flat: ModelCatalogItem[] = []
    const push = (arr: ModelCatalogItem[]) => {
      for (const m of arr) {
        if (!seen.has(m.id)) { seen.add(m.id); flat.push(m) }
      }
    }
    // order: recommended then groups in order
    push(recommended)
    for (const [, groupModels] of groupedByBand) {
      push(groupModels)
    }
    return flat
  }, [recommended, groupedByBand])

  const flatList = useMemo(() => getFlatFiltered(), [getFlatFiltered])

  // keyboard nav
  const onKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
        e.preventDefault()
        setOpen(true)
      }
      return
    }
    const len = flatList.length
    if (len === 0) return

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setFocusedIdx(prev => (prev + 1) % len)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setFocusedIdx(prev => (prev - 1 + len) % len)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const item = flatList[focusedIdx]
      if (item) {
        onSelect(item)
        setOpen(false)
      }
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
    }
  }, [open, flatList, focusedIdx, onSelect])

  // scroll focused into view
  useEffect(() => {
    if (!open) return
    const el = listRef.current?.querySelector(`[data-idx="${focusedIdx}"]`) as HTMLElement | null
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [focusedIdx, open])

  const handleSelect = (m: ModelCatalogItem) => {
    onSelect(m)
    setOpen(false)
  }

  if (loading) {
    return (
      <div className="model-picker-root">
        <div className="model-picker-trigger model-picker-trigger-loading">
          <span className="model-picker-trigger-skeleton" />
        </div>
      </div>
    )
  }

  const selectedHealth = selected ? healthOf(selected) : null

  return (
    <div className="model-picker-root" ref={rootRef} dir={dirFor(lang)} onKeyDown={onKeyDown}>
      {/* Trigger */}
      <button
        ref={triggerRef}
        type="button"
        className={`model-picker-trigger ${open ? 'model-picker-trigger-open' : ''} ${disabled ? 'model-picker-trigger-disabled' : ''}`}
        onClick={() => {
          if (disabled) return
          setOpen(o => !o)
        }}
        aria-haspopup="dialog"
        aria-expanded={open}
        dir="ltr"
        data-testid="model-picker-trigger"
      >
        <span className="model-picker-trigger-icon" aria-hidden>
          {selected ? getModelIcon(selected.capabilities, selected.recommendedFor) : '🤖'}
        </span>
        <span className="model-picker-trigger-main">
          <span className="model-picker-trigger-name" dir="ltr" title={selected?.displayName || s.noModelSelected}>
            {selected?.displayName || s.noModelSelected}
          </span>
          <span className="model-picker-trigger-sub">
            {selected ? (
              <>
                <span className="model-picker-trigger-ctx" dir="ltr">{formatContextWindow(selected.contextWindow)} ctx</span>
                {selectedHealth && (
                  <span
                    className="model-health-dot"
                    style={{ background: HEALTH_TONE[selectedHealth.status] }}
                    title={s.statusLabel(health[selectedHealth.status])}
                    aria-label={s.statusLabel(health[selectedHealth.status])}
                  />
                )}
              </>
            ) : (
              <span className="text-muted">—</span>
            )}
          </span>
        </span>
        <span className={`model-picker-chevron ${open ? 'model-picker-chevron-open' : ''}`} aria-hidden>
          <Icon name="arrowLeft" size={14} />
        </span>
      </button>

      {open && (
        <>
          <div className="model-picker-overlay" onClick={() => setOpen(false)} />
          <div
            ref={dropdownRef}
            className="model-picker-dropdown"
            role="dialog"
            aria-label={s.selectModel}
            dir={dirFor(lang)}
          >
            {/* Header: search + smart note */}
            <div className="model-picker-header">
              {smartModeActive && (
                <div className="model-picker-smart-note" dir={dirFor(lang)}>
                  <span>🧠 {s.smartModeNote}</span>
                </div>
              )}
              <div className="model-picker-search-wrapper">
                <span className="model-picker-search-icon"><Icon name="search" size={16} /></span>
                <input
                  ref={inputRef}
                  type="text"
                  className="model-picker-search"
                  placeholder={s.searchPlaceholder}
                  value={query}
                  onChange={e => {
                    setQuery(e.target.value)
                    setFocusedIdx(0)
                  }}
                  dir={dirFor(lang)}
                  data-testid="model-picker-search"
                />
                {query && (
                  <button className="model-picker-search-clear" onClick={() => { setQuery(''); setFocusedIdx(0); inputRef.current?.focus() }}>
                    <Icon name="close" size={14} />
                  </button>
                )}
              </div>
            </div>

            <div className="model-picker-list" ref={listRef}>
              {flatList.length === 0 ? (
                <div className="model-picker-empty">
                  <Icon name="search" size={20} className="text-muted" />
                  <span>{s.noModelFound(query)}</span>
                </div>
              ) : (
                <>
                  {recommended.length > 0 && (
                    <div className="model-picker-section">
                      <div className="model-picker-section-title">
                        <span>⭐ {s.recommended}</span>
                        <span className="model-picker-section-count">{f.num(recommended.length)}</span>
                      </div>
                      <div className="model-picker-cards">
                        {recommended.map(m => {
                          const flatIdx = flatList.findIndex(x => x.id === m.id)
                          const isSel = selected?.id === m.id
                          const isFocused = flatIdx === focusedIdx
                          const w = healthOf(m).status
                          return (
                            <ModelCard
                              key={`rec-${m.id}`}
                              model={m}
                              isSelected={isSel}
                              isFocused={isFocused}
                              healthStatus={w}
                              focusIdx={flatIdx}
                              onClick={() => handleSelect(m)}
                            />
                          )
                        })}
                      </div>
                    </div>
                  )}

                  <div className="model-picker-section">
                    <div className="model-picker-section-title">
                      <span>{s.allModels}</span>
                      <span className="model-picker-section-count">{f.num(filtered.length)}</span>
                    </div>

                    {groupedByBand.map(([band, groupModels]) => (
                      <div key={band} className="model-picker-provider-group">
                        {groupedByBand.length > 1 && (
                          <div className="model-picker-provider-group-title">
                            <span className="model-provider-badge">
                                                            {priceBandLabel(band, lang)}
                            </span>
                            <span className="text-muted" style={{ fontSize: '10px' }}>{s.modelsCount(f.num(groupModels.length))}</span>
                          </div>
                        )}
                        <div className="model-picker-cards">
                          {groupModels.map(m => {
                            const flatIdx = flatList.findIndex(x => x.id === m.id)
                            // avoid duplicate highlight already in recommended? still show, but distinguish
                            const isSel = selected?.id === m.id
                            const isFocused = flatIdx === focusedIdx
                            const w = healthOf(m).status
                            return (
                              <ModelCard
                                key={`${band}-${m.id}`}
                                model={m}
                                isSelected={isSel}
                                isFocused={isFocused}
                                healthStatus={w}
                                focusIdx={flatIdx}
                                onClick={() => handleSelect(m)}
                              />
                            )
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>

            <div className="model-picker-footer" dir={dirFor(lang)}>
              <span className="model-picker-footer-hint"><kbd>↑↓</kbd> {s.navigate} · <kbd>Enter</kbd> {s.select} · <kbd>Esc</kbd> {s.close}</span>
              <span className="model-picker-footer-count">{s.modelsCount(f.num(models.length))}</span>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function ModelCard({ model: m, isSelected, isFocused, healthStatus, focusIdx, onClick }: {
  model: ModelCatalogItem
  isSelected: boolean
  isFocused: boolean
  healthStatus: HealthStatus
  focusIdx: number
  onClick: () => void
}) {
  const lang = useLang()
  const s = modelPickerStrings(lang)
  const health = healthLabel(lang)
  const icon = getModelIcon(m.capabilities, m.recommendedFor)
  return (
    <button
      type="button"
      className={`model-card ${isSelected ? 'model-card-selected' : ''} ${isFocused ? 'model-card-focused' : ''}`}
      onClick={onClick}
      data-idx={focusIdx}
      data-model-id={m.id}
      dir={dirFor(lang)}
      role="option"
      aria-selected={isSelected}
    >
      {isSelected && <span className="model-card-check" aria-hidden><Icon name="check" size={12} /></span>}
      <div className="model-card-header">
        <div className="model-card-title-row">
          <span className="model-card-icon" aria-hidden>{icon}</span>
          <div className="model-card-title-col">
            <span className="model-card-name" dir="ltr">{m.displayName}</span>
            <span className="model-card-id" dir="ltr">{m.id}</span>
          </div>
        </div>
        {/* Reports measured health rather than a yes/no guess from a static
            list, so "unknown" is now distinguishable from "degraded". */}
        <span className={`model-health-badge model-health-${healthStatus}`}>
          <span className="model-health-dot" style={{ background: HEALTH_TONE[healthStatus] }} />
          {health[healthStatus]}
        </span>
      </div>

      {/* The whole row is an LTR island: model ids, `128K ctx` and the
          capability names are all Latin, and mixing them into the RTL
          paragraph reorders the unit in front of its number. Latin digits are
          deliberate *inside* this island — a Persian numeral followed by a
          Latin unit inside an LTR run has the same reordering problem in
          reverse. Everywhere outside the picker, numerals are Persian. */}
      <div className="model-card-meta" dir="ltr">
        <span className="model-card-ctx">{formatContextWindow(m.contextWindow)} ctx</span>
        {(m.capabilities || []).slice(0, 3).map(c => (
          <span key={c} className="model-capability-tag">{c}</span>
        ))}
      </div>

      {m.description && (
        <div className="model-card-desc" dir={dirFor(lang)} title={m.description}>
          {m.description.length > 90 ? m.description.slice(0, 90) + '…' : m.description}
        </div>
      )}

      {/* dir stays with the document: the labels and the unit follow the
          panel's own language, so forcing LTR here would put the unit word
          on the wrong side of its amount. */}
      <div className="model-card-pricing">
        <span className="model-card-pricing-item" title={s.inputPricing}>
          <span className="model-card-pricing-label">{s.input}</span>
          <span className="model-card-pricing-value">{formatPriceIRT(m.pricing?.inputPerMillion ?? 0, lang)}</span>
        </span>
        <span className="model-card-pricing-sep">·</span>
        <span className="model-card-pricing-item" title={s.outputPricing}>
          <span className="model-card-pricing-label">{s.output}</span>
          <span className="model-card-pricing-value">{formatPriceIRT(m.pricing?.outputPerMillion ?? 0, lang)}</span>
        </span>
      </div>
    </button>
  )
}
