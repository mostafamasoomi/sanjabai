'use client'

import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { type ModelCatalogItem } from '@/types/catalog'
import { Icon } from '@/components/ui/Icon'
import {
  WORKING_MODEL_IDS,
  isWorkingModel,
  getModelIcon,
  formatPriceIRT,
  formatContextWindow,
  getProviderLabel,
  isRecommendedModel,
} from './modelUtils'

const STORAGE_KEY = 'multiai_selected_model'

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
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [focusedIdx, setFocusedIdx] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

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

  const filtered = useMemo(() => {
    const q = normalize(query)
    if (!q) return models
    return models.filter(m => {
      const hay = [
        m.displayName,
        m.id,
        m.provider,
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

  const groupedByProvider = useMemo(() => {
    const map = new Map<string, ModelCatalogItem[]>()
    for (const m of filtered) {
      const key = m.provider || 'other'
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(m)
    }
    // sort providers: bynara/mistral/tenc... first, then alpha
    const entries = Array.from(map.entries())
    const priority = ['bynara', 'mistral', 'tencent', 'kimi', 'openai', 'google', 'anthropic', 'xai']
    entries.sort((a, b) => {
      const ai = priority.indexOf(a[0].toLowerCase())
      const bi = priority.indexOf(b[0].toLowerCase())
      if (ai !== -1 && bi !== -1) return ai - bi
      if (ai !== -1) return -1
      if (bi !== -1) return 1
      return a[0].localeCompare(b[0])
    })
    return entries
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
    for (const [, groupModels] of groupedByProvider) {
      push(groupModels)
    }
    return flat
  }, [recommended, groupedByProvider])

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

  const working = selected ? isWorkingModel(selected.id) : false

  return (
    <div className="model-picker-root" ref={rootRef} dir="rtl" onKeyDown={onKeyDown}>
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
          <span className="model-picker-trigger-name" dir="ltr" title={selected?.displayName || 'انتخاب مدل'}>
            {selected?.displayName || 'انتخاب مدل'}
          </span>
          <span className="model-picker-trigger-sub">
            {selected ? (
              <>
                <span className="model-picker-trigger-ctx" dir="ltr">{formatContextWindow(selected.contextWindow)} ctx</span>
                <span className={`model-working-dot ${working ? 'model-working-dot-yes' : 'model-working-dot-warn'}`} title={working ? 'کار می‌کند' : 'ممکن است محدود باشد'}>
                  {working ? '✅' : '⚠️'}
                </span>
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
          <div role="button" tabIndex={0} className="model-picker-overlay" onClick={() => setOpen(false)} />
          <div
            className="model-picker-dropdown"
            role="dialog"
            aria-label="انتخاب مدل"
            dir="rtl"
          >
            {/* Header: search + smart note */}
            <div className="model-picker-header">
              {smartModeActive && (
                <div className="model-picker-smart-note" dir="rtl">
                  <span>🧠 Smart Mode فعال — انتخاب خودکار مدل</span>
                </div>
              )}
              <div className="model-picker-search-wrapper">
                <span className="model-picker-search-icon"><Icon name="search" size={16} /></span>
                <input
                  ref={inputRef}
                  type="text"
                  className="model-picker-search"
                  placeholder="جستجوی مدل، ارائه‌دهنده، قابلیت..."
                  value={query}
                  onChange={e => {
                    setQuery(e.target.value)
                    setFocusedIdx(0)
                  }}
                  dir="rtl"
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
                  <span>مدلی با &quot;{query}&quot; یافت نشد</span>
                </div>
              ) : (
                <>
                  {recommended.length > 0 && (
                    <div className="model-picker-section">
                      <div className="model-picker-section-title">
                        <span>⭐ پیشنهادی</span>
                        <span className="model-picker-section-count">{recommended.length}</span>
                      </div>
                      <div className="model-picker-cards">
                        {recommended.map(m => {
                          const flatIdx = flatList.findIndex(x => x.id === m.id)
                          const isSel = selected?.id === m.id
                          const isFocused = flatIdx === focusedIdx
                          const w = isWorkingModel(m.id)
                          return (
                            <ModelCard
                              key={`rec-${m.id}`}
                              model={m}
                              isSelected={isSel}
                              isFocused={isFocused}
                              isWorking={w}
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
                      <span>همه مدلها</span>
                      <span className="model-picker-section-count">{filtered.length}</span>
                    </div>

                    {groupedByProvider.map(([provider, groupModels]) => (
                      <div key={provider} className="model-picker-provider-group">
                        {groupedByProvider.length > 1 && (
                          <div className="model-picker-provider-group-title" dir="ltr">
                            <span className="model-provider-badge">{getProviderLabel(provider)}</span>
                            <span className="text-muted" style={{ fontSize: '10px' }}>{groupModels.length} مدل</span>
                          </div>
                        )}
                        <div className="model-picker-cards">
                          {groupModels.map(m => {
                            const flatIdx = flatList.findIndex(x => x.id === m.id)
                            // avoid duplicate highlight already in recommended? still show, but distinguish
                            const isSel = selected?.id === m.id
                            const isFocused = flatIdx === focusedIdx
                            const w = isWorkingModel(m.id)
                            return (
                              <ModelCard
                                key={`${provider}-${m.id}`}
                                model={m}
                                isSelected={isSel}
                                isFocused={isFocused}
                                isWorking={w}
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

            <div className="model-picker-footer" dir="rtl">
              <span className="model-picker-footer-hint"><kbd>↑↓</kbd> پیمایش · <kbd>Enter</kbd> انتخاب · <kbd>Esc</kbd> بستن</span>
              <span className="model-picker-footer-count" dir="ltr">{models.length} models</span>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function ModelCard({ model: m, isSelected, isFocused, isWorking, focusIdx, onClick }: {
  model: ModelCatalogItem
  isSelected: boolean
  isFocused: boolean
  isWorking: boolean
  focusIdx: number
  onClick: () => void
}) {
  const icon = getModelIcon(m.capabilities, m.recommendedFor)
  return (
    <button
      type="button"
      className={`model-card ${isSelected ? 'model-card-selected' : ''} ${isFocused ? 'model-card-focused' : ''}`}
      onClick={onClick}
      data-idx={focusIdx}
      data-model-id={m.id}
      dir="rtl"
      role="option"
      aria-selected={isSelected}
    >
      {isSelected && <span className="model-card-check model-card-header" aria-hidden><Icon name="check" size={12} /></span>}
      <div >
        <div className="model-card-title-row">
          <span className="model-card-icon" aria-hidden>{icon}</span>
          <div className="model-card-title-col">
            <span className="model-card-name" dir="ltr">{m.displayName}</span>
            <span className="model-card-id" dir="ltr">{m.id}</span>
          </div>
        </div>
        <span className={`model-working-badge ${isWorking ? 'model-working-yes' : 'model-working-warn'}`}>
          {isWorking ? '✅ کار می‌کند' : '⚠️ محدود'}
        </span>
      </div>

      <div className="model-card-meta" dir="ltr">
        <span className="model-card-ctx">{formatContextWindow(m.contextWindow)} ctx</span>
        {(m.capabilities || []).slice(0, 3).map(c => (
          <span key={c} className="model-capability-tag">{c}</span>
        ))}
      </div>

      {m.description && (
        <div className="model-card-desc" dir="rtl" title={m.description}>
          {m.description.length > 90 ? m.description.slice(0, 90) + '…' : m.description}
        </div>
      )}

      <div className="model-card-pricing" dir="ltr">
        <span className="model-card-pricing-item" title="ورودی">
          <span className="model-card-pricing-label">in:</span>
          <span className="model-card-pricing-value">{formatPriceIRT(m.pricing?.inputPerMillion ?? 0)}</span>
        </span>
        <span className="model-card-pricing-sep">·</span>
        <span className="model-card-pricing-item" title="خروجی">
          <span className="model-card-pricing-label">out:</span>
          <span className="model-card-pricing-value">{formatPriceIRT(m.pricing?.outputPerMillion ?? 0)}</span>
        </span>
      </div>
    </button>
  )
}
