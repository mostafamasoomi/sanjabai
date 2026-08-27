'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt, dirFor } from '@/lib/i18n'
import { priceBand, priceBandLabel, PRICE_BAND_ORDER, type PriceBand } from '@/lib/useCatalog'
import type { ModelCatalogItem } from '@/types/catalog'
import { comboStrings } from './ComboManager.strings'

/* ═══════════════════════════════════════════════════════════════════════
   Combo editor — create or edit one combo.

   Mirrors the server's rules (backend/combos.py) so the user is stopped by
   a disabled control with an explanation rather than by a 400. The server
   is still the enforcement; this only removes the surprise.

   Ordering is up/down buttons, not drag-and-drop, on purpose: a combo holds
   2–5 rows, arrows are reachable from the keyboard, and "up/down" is
   unambiguous in an RTL layout where "left/right" is not.
   ═══════════════════════════════════════════════════════════════════════ */

export const MIN_ITEMS = 2
export const MAX_ITEMS = 5
export const MAX_COMBOS = 10
export const MAX_NAME_LEN = 60

export type ComboPolicy = 'sequential' | 'round_robin'
export const COMBO_POLICIES: ComboPolicy[] = ['sequential', 'round_robin']

/** As returned by GET/POST/PUT /me/combos — `model_public_id` is the public
 *  `sanjab/...` id the user picked, never a provider route. */
export type ComboItem = { position: number; model_public_id: string }

export type Combo = {
  id: number
  name: string
  policy: ComboPolicy
  enabled: boolean
  created_at: string | null
  updated_at: string | null
  items: ComboItem[]
}

/** What the editor hands back. `items` is public ids in the order the user
 *  arranged them; the server derives `position` from that order. */
export type ComboDraft = {
  name: string
  policy: ComboPolicy
  enabled: boolean
  items: string[]
}

export function indexModels(models: ModelCatalogItem[]): Map<string, ModelCatalogItem> {
  return new Map(models.map((m) => [m.id, m]))
}

type Props = {
  open: boolean
  /** null = create a new combo. */
  initial: Combo | null
  models: ModelCatalogItem[]
  catalogLoading: boolean
  catalogError: boolean
  saving: boolean
  /** The server's own Persian `detail`, surfaced verbatim. */
  errorMessage: string | null
  onCancel: () => void
  onSubmit: (draft: ComboDraft) => void
}

export default function ComboEditor({
  open, initial, models, catalogLoading, catalogError, saving, errorMessage, onCancel, onSubmit,
}: Props) {
  const lang = useLang()
  const s = comboStrings(lang)
  const f = fmt(lang)

  const [name, setName] = useState('')
  const [policy, setPolicy] = useState<ComboPolicy>('sequential')
  const [enabled, setEnabled] = useState(true)
  const [items, setItems] = useState<string[]>([])
  const [pickerOpen, setPickerOpen] = useState(false)
  const [query, setQuery] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)

  // Reload the form whenever a different combo (or "create") is opened.
  useEffect(() => {
    if (!open) return
    setName(initial?.name ?? '')
    setPolicy(initial?.policy ?? 'sequential')
    setEnabled(initial?.enabled ?? true)
    setItems((initial?.items ?? []).map((it) => it.model_public_id))
    setPickerOpen(false)
    setQuery('')
  }, [open, initial])

  // Escape backs out one layer at a time: the picker first, then the modal.
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      if (pickerOpen) setPickerOpen(false)
      else if (!saving) onCancel()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, pickerOpen, saving, onCancel])

  useEffect(() => {
    if (pickerOpen) setTimeout(() => searchRef.current?.focus(), 50)
  }, [pickerOpen])

  const byId = useMemo(() => indexModels(models), [models])

  // Models the backend measured as down are dropped before anything else:
  // offering one guarantees a rejected save. `unknown` (unexercised) and
  // `degraded` (still answers) stay.
  const selectable = useMemo(
    () => models.filter((m) => m.health?.status !== 'down' && !items.includes(m.id)),
    [models, items],
  )

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return selectable
    return selectable.filter((m) =>
      `${m.displayName} ${m.id} ${m.description || ''}`.toLowerCase().includes(q),
    )
  }, [selectable, query])

  const grouped = useMemo(() => {
    const map = new Map<PriceBand, ModelCatalogItem[]>()
    for (const m of filtered) {
      const band = priceBand(m, filtered)
      if (!map.has(band)) map.set(band, [])
      map.get(band)!.push(m)
    }
    return PRICE_BAND_ORDER.filter((b) => map.has(b)).map(
      (b) => [b, map.get(b)!] as [PriceBand, ModelCatalogItem[]],
    )
  }, [filtered])

  if (!open) return null

  const trimmed = name.trim()
  const atMaxItems = items.length >= MAX_ITEMS
  const nameOk = trimmed.length >= 1 && trimmed.length <= MAX_NAME_LEN
  const itemsOk = items.length >= MIN_ITEMS && items.length <= MAX_ITEMS
  const canSave = nameOk && itemsOk && !saving

  const move = (from: number, to: number) => {
    if (to < 0 || to >= items.length) return
    const next = [...items]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    setItems(next)
  }

  const addModel = (id: string) => {
    if (atMaxItems || items.includes(id)) return
    setItems([...items, id])
    setQuery('')
    // Closing on the 5th pick avoids leaving an all-disabled list on screen.
    if (items.length + 1 >= MAX_ITEMS) setPickerOpen(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" dir={dirFor(lang)}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => !saving && onCancel()} />
      <div
        className="relative bg-[var(--bg-elevated)] border border-[var(--border-strong)] rounded-[var(--radius-xl)] p-6 max-w-xl w-full shadow-xl fade-in overflow-y-auto max-h-[90vh]"
        role="dialog"
        aria-modal="true"
        aria-label={initial ? s.editTitle : s.createTitle}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <h2 className="card-title">{initial ? s.editTitle : s.createTitle}</h2>
          <button onClick={onCancel} disabled={saving} className="btn btn-ghost btn-sm" aria-label={s.closeAria}>
            <Icon name="close" size={16} />
          </button>
        </div>

        {/* Name */}
        <label style={{ display: 'block', marginBottom: 16 }}>
          <span style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>{s.nameLabel}</span>
          <input
            className="input w-full"
            value={name}
            maxLength={MAX_NAME_LEN}
            placeholder={s.namePlaceholder}
            onChange={(e) => setName(e.target.value)}
          />
          <span style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
            {s.nameHint(f.num(MAX_NAME_LEN))}
          </span>
        </label>

        {/* Policy — each option carries its own plain-language explanation, so
            the difference is readable without a docs page. */}
        <fieldset style={{ border: 0, padding: 0, margin: '0 0 16px' }}>
          <legend style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>{s.policyLabel}</legend>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {COMBO_POLICIES.map((p) => (
              <label
                key={p}
                className="card"
                style={{
                  display: 'flex', gap: 10, alignItems: 'flex-start', padding: 12, cursor: 'pointer',
                  borderColor: policy === p ? 'var(--accent)' : undefined,
                }}
              >
                <input
                  type="radio"
                  name="combo-policy"
                  checked={policy === p}
                  onChange={() => setPolicy(p)}
                  style={{ marginTop: 3 }}
                />
                <span>
                  <span style={{ display: 'block', fontWeight: 700, fontSize: 13 }}>
                    {p === 'sequential' ? s.policySequential : s.policyRoundRobin}
                  </span>
                  <span style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginTop: 2, lineHeight: 1.7 }}>
                    {p === 'sequential' ? s.policySequentialDesc : s.policyRoundRobinDesc}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        {/* Ordered items */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>{s.modelsLabel}</span>
          <span className="badge badge-accent">{s.itemsCount(f.num(items.length), f.num(MAX_ITEMS))}</span>
        </div>

        <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {items.map((id, idx) => {
            const model = byId.get(id)
            const label = model?.displayName || id
            return (
              <li key={id} className="card" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 10 }}>
                <span className="badge">{f.num(idx + 1)}</span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ display: 'block', fontSize: 13, fontWeight: 600 }} dir="ltr">{label}</span>
                  {!model && (
                    <span style={{ display: 'block', fontSize: 11, color: 'var(--warning)' }}>{s.unavailableModel}</span>
                  )}
                </span>
                <button
                  type="button" className="btn btn-ghost btn-sm" aria-label={s.moveUp} title={s.moveUp}
                  disabled={idx === 0} onClick={() => move(idx, idx - 1)}
                >↑</button>
                <button
                  type="button" className="btn btn-ghost btn-sm" aria-label={s.moveDown} title={s.moveDown}
                  disabled={idx === items.length - 1} onClick={() => move(idx, idx + 1)}
                >↓</button>
                <button
                  type="button" className="btn btn-ghost btn-sm" aria-label={s.removeItem(label)} title={s.removeItem(label)}
                  onClick={() => setItems(items.filter((x) => x !== id))}
                >
                  <Icon name="trash" size={14} />
                </button>
              </li>
            )
          })}
        </ol>

        <p style={{ fontSize: 11, color: atMaxItems ? 'var(--warning)' : 'var(--text-muted)', margin: '8px 0' }}>
          {atMaxItems
            ? s.itemsMaxReached(f.num(MAX_ITEMS))
            : items.length < MIN_ITEMS
              ? s.itemsMinNotMet(f.num(MIN_ITEMS))
              : s.itemsRangeHint(f.num(MIN_ITEMS), f.num(MAX_ITEMS))}
        </p>

        <button
          type="button"
          className="btn btn-sm"
          disabled={atMaxItems}
          title={atMaxItems ? s.itemsMaxReached(f.num(MAX_ITEMS)) : undefined}
          onClick={() => setPickerOpen((o) => !o)}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
        >
          <Icon name="plus" size={14} />
          {s.addModel}
        </button>

        {pickerOpen && !atMaxItems && (
          <div className="card" style={{ marginTop: 10, padding: 12 }} aria-label={s.pickerTitle}>
            <input
              ref={searchRef}
              className="input w-full"
              placeholder={s.searchPlaceholder}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={{ marginBottom: 10 }}
            />
            {catalogLoading ? (
              <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>{s.catalogLoading}</p>
            ) : catalogError ? (
              <p style={{ fontSize: 12, color: 'var(--danger)' }}>{s.catalogError}</p>
            ) : filtered.length === 0 ? (
              <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {selectable.length === 0 ? s.allAdded : s.noModelFound}
              </p>
            ) : (
              <div style={{ maxHeight: 240, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
                {grouped.map(([band, group]) => (
                  <div key={band}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                      <span className="badge badge-accent">{priceBandLabel(band, lang)}</span>
                      <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{s.modelsCount(f.num(group.length))}</span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {group.map((m) => (
                        <button
                          key={m.id}
                          type="button"
                          className="btn btn-ghost btn-sm"
                          style={{ justifyContent: 'flex-start', width: '100%' }}
                          onClick={() => addModel(m.id)}
                        >
                          {/* The public `sanjab/...` id — never a provider route. */}
                          <span dir="ltr" style={{ fontSize: 12 }}>{m.displayName}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Enabled */}
        <div className="profile-toggle-row" style={{ marginTop: 12 }}>
          <span>
            <span style={{ display: 'block', fontWeight: 600, fontSize: 13 }}>{s.enabledLabel}</span>
            <span style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)' }}>{s.enabledHint}</span>
          </span>
          <button
            type="button"
            className={`profile-toggle ${enabled ? 'active' : ''}`}
            role="switch"
            aria-checked={enabled}
            aria-label={s.enabledLabel}
            onClick={() => setEnabled(!enabled)}
          >
            <span className="profile-toggle-knob" />
          </button>
        </div>

        {/* The server's own Persian refusal, not a message invented here. */}
        {errorMessage && (
          <p role="alert" style={{ fontSize: 12, color: 'var(--danger)', marginTop: 12 }}>{errorMessage}</p>
        )}

        <div style={{ display: 'flex', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}>{s.cancel}</button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canSave}
            onClick={() => onSubmit({ name: trimmed, policy, enabled, items })}
          >
            {saving ? s.saving : s.save}
          </button>
        </div>
      </div>
    </div>
  )
}
