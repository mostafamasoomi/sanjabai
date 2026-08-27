'use client'

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import Link from 'next/link'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { dirFor, fmt } from '@/lib/i18n'
import { smartModePopoverStrings } from './SmartModePopover.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Smart Mode selector — off / automatic / smart router / one of my combos.

   Replaces the plain on-off switch that used to live inline in
   ChatModelBar.tsx. The strategy travels to the backend as the `X-Smart-Mode`
   request header (`auto` | `router` | `combo:<id>`); the backend answers with
   an SSE `smart_info` event carrying the mode that ACTUALLY ran, which is not
   necessarily the one asked for — a combo (or the router) may decline and the
   rule-based pick takes over. `ranMode` is that answer, and this component
   says so out loud rather than leaving the trigger claiming "combo".

   Popover idiom copied from ModelPicker.tsx: own `open` state, outside-click
   on a rootRef, Escape to close, role="dialog".
   ═══════════════════════════════════════════════════════════════════════════ */

/** What the user asked for. Sent verbatim as `X-Smart-Mode` when smart mode
 *  is on; `off` is not a strategy, it is the absence of one (smartMode=false). */
export type SmartStrategy = 'auto' | 'router' | `combo:${number}`

/** The on/off flag keeps its original key and its original `'true'|'false'`
 *  value, so a returning user's stored boolean still means exactly what it
 *  meant. The strategy is a SIBLING key: absent (every pre-existing user)
 *  reads back as 'auto', which is the behaviour that boolean already had. A
 *  migration that silently promoted anyone into the metered router would be
 *  spending their money for them. */
const ON_KEY = 'sanjabai_smart_mode'
const STRATEGY_KEY = 'sanjabai_smart_mode_strategy'

export function parseSmartStrategy(raw: string | null): SmartStrategy {
  if (raw === 'router') return 'router'
  const m = /^combo:(\d+)$/.exec(raw || '')
  return m ? (`combo:${Number(m[1])}` as SmartStrategy) : 'auto'
}

export function loadSmartMode(): { on: boolean; strategy: SmartStrategy } {
  try {
    return {
      on: localStorage.getItem(ON_KEY) === 'true',
      strategy: parseSmartStrategy(localStorage.getItem(STRATEGY_KEY)),
    }
  } catch {
    return { on: false, strategy: 'auto' }
  }
}

export function persistSmartMode(on: boolean, strategy: SmartStrategy): void {
  try {
    localStorage.setItem(ON_KEY, on ? 'true' : 'false')
    localStorage.setItem(STRATEGY_KEY, strategy)
  } catch { /* private mode / quota — the in-memory choice still works */ }
}

function comboIdOf(strategy: SmartStrategy): number | null {
  const m = /^combo:(\d+)$/.exec(strategy)
  return m ? Number(m[1]) : null
}

type ComboOption = { id: number; name: string; count: number }
type LoadState = 'idle' | 'loading' | 'ready' | 'error'

type Props = {
  token: string | null
  smartMode: boolean
  setSmartMode: (updater: (prev: boolean) => boolean) => void
  strategy: SmartStrategy
  setStrategy: (v: SmartStrategy) => void
  /** `mode` from the last `smart_info` SSE event — what really ran. */
  ranMode: string | null
}

export default function SmartModePopover({
  token, smartMode, setSmartMode, strategy, setStrategy, ranMode,
}: Props) {
  const lang = useLang()
  const s = smartModePopoverStrings(lang)
  const f = fmt(lang)
  const rootRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [combos, setCombos] = useState<ComboOption[]>([])
  const [state, setState] = useState<LoadState>('idle')
  const requestedRef = useRef(false)

  // Only enabled combos are offerable, so the list is fetched lazily: when the
  // popover is opened, or straight away when a combo is already the choice
  // (the trigger has to be able to name it).
  const wantCombos = open || strategy.startsWith('combo:')
  useEffect(() => {
    if (!wantCombos || !token || requestedRef.current) return
    requestedRef.current = true
    setState('loading')
    fetch('/api/me/combos', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error('combos'))))
      .then((body: { combos?: Array<{ id: number; name: string; enabled: boolean; items?: unknown[] }> }) => {
        const list = Array.isArray(body?.combos) ? body.combos : []
        setCombos(list.filter(c => c?.enabled).map(c => ({
          id: c.id, name: c.name, count: Array.isArray(c.items) ? c.items.length : 0,
        })))
        setState('ready')
      })
      .catch(() => {
        // Retried the next time the popover opens; off/auto/router keep working.
        requestedRef.current = false
        setState('error')
      })
  }, [wantCombos, token])

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const selectedComboId = comboIdOf(strategy)
  const selectedCombo = useMemo(
    () => (selectedComboId == null ? null : combos.find(c => c.id === selectedComboId) || null),
    [combos, selectedComboId],
  )
  // A combo the user deleted or disabled elsewhere: still the stored choice,
  // but no longer in the list. Say so instead of showing a blank name.
  const comboGone = selectedComboId != null && state === 'ready' && !selectedCombo

  const labelOf = useCallback((mode: string): string => {
    if (mode === 'router') return s.ranRouter
    const m = /^combo:(\d+)$/.exec(mode)
    if (!m) return s.ranAuto
    const found = combos.find(c => c.id === Number(m[1]))
    return found ? found.name : s.comboUnknown(f.num(Number(m[1])))
  }, [combos, f, s])

  const triggerLabel = !smartMode ? s.triggerOff : s.trigger(labelOf(strategy))
  // The backend answers with what ran; a mismatch means the ask was declined.
  const fellBack = smartMode && !!ranMode && ranMode !== strategy

  const choose = (on: boolean, next: SmartStrategy) => {
    setSmartMode(() => on)
    setStrategy(next)
    setOpen(false)
  }

  return (
    <div
      className="relative"
      ref={rootRef}
      dir={dirFor(lang)}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
    >
      <button
        type="button"
        className="smart-mode-toggle"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
        title={s.open}
        // globals.css tints the old switch through `[aria-checked='true']`,
        // which no longer applies: this trigger opens a dialog, it is not a
        // checkbox, and aria-checked on role=button is invalid ARIA. The
        // on-state tint is inline instead; the label already says the state.
        style={smartMode ? { color: 'var(--accent)' } : undefined}
      >
        <span className={`smart-mode-switch ${smartMode ? 'smart-mode-on' : ''}`} aria-hidden>
          <span className="smart-mode-knob" />
        </span>
        <span className="select-none">{triggerLabel}</span>
        <Icon name="arrowLeft" size={12} />
      </button>

      {fellBack && (
        <span
          className="badge text-[9px]"
          style={{ color: 'var(--warning)', marginInlineStart: 4 }}
          title={s.fellBack(labelOf(strategy), labelOf(ranMode!))}
        >
          <Icon name="warning" size={10} /> {s.fellBackShort}
        </span>
      )}

      {open && (
        <div
          className="export-dropdown"
          role="dialog"
          aria-label={s.title}
          dir={dirFor(lang)}
          style={{ width: 300, maxWidth: 'calc(100vw - 24px)', maxHeight: '70vh', overflowY: 'auto' }}
        >
          <div role="radiogroup" aria-label={s.title}>
            <Row
              checked={!smartMode}
              title={s.offLabel}
              desc={s.offDesc}
              onClick={() => choose(false, strategy)}
            />
            <Row
              checked={smartMode && strategy === 'auto'}
              title={s.autoLabel}
              desc={s.autoDesc}
              onClick={() => choose(true, 'auto')}
            />
            <Row
              checked={smartMode && strategy === 'router'}
              title={s.routerLabel}
              desc={s.routerDesc}
              note={s.routerCost}
              hint={s.routerFallbackNote}
              onClick={() => choose(true, 'router')}
            />
          </div>

          <div style={{ borderTop: '1px solid var(--border)', margin: '6px 0' }} />

          <div style={{ padding: '2px 10px 6px', fontSize: 11, color: 'var(--text-muted)' }}>
            {s.combosHeading}
          </div>

          {state === 'loading' && (
            <div style={NOTE_STYLE}>{s.combosLoading}</div>
          )}
          {state === 'error' && (
            <div style={{ ...NOTE_STYLE, color: 'var(--danger)' }}>{s.combosError}</div>
          )}
          {/* `idle` with no token never becomes `loading` (nothing to fetch
              against), so it is an empty list, not a pending one. */}
          {combos.length === 0 && (state === 'ready' || (state === 'idle' && !token)) && (
            <div style={NOTE_STYLE}>{s.combosEmpty}</div>
          )}
          {comboGone && (
            <div style={{ ...NOTE_STYLE, color: 'var(--warning)' }}>{s.comboMissing}</div>
          )}

          {combos.length > 0 && (
            <div role="radiogroup" aria-label={s.combosHeading}>
              {combos.map(c => (
                <Row
                  key={c.id}
                  checked={smartMode && selectedComboId === c.id}
                  title={c.name}
                  desc={s.comboItems(f.num(c.count))}
                  onClick={() => choose(true, `combo:${c.id}` as SmartStrategy)}
                />
              ))}
            </div>
          )}

          <Link
            href="/combos"
            className="export-dropdown-item no-underline"
            onClick={() => setOpen(false)}
          >
            <Icon name="settings" size={14} /> {s.combosManage}
          </Link>
        </div>
      )}
    </div>
  )
}

const NOTE_STYLE = { padding: '4px 10px 8px', fontSize: 11, lineHeight: 1.8, color: 'var(--text-muted)' } as const

function Row({ checked, title, desc, note, hint, onClick }: {
  checked: boolean
  title: string
  desc: string
  /** The paid-for consequence of this choice, shown before it is picked. */
  note?: string
  hint?: string
  onClick: () => void
}): ReactNode {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={checked}
      onClick={onClick}
      className="export-dropdown-item"
      style={{ alignItems: 'flex-start', gap: 8, padding: '8px 10px' }}
    >
      <span style={{ width: 14, flexShrink: 0, marginTop: 2, color: 'var(--accent)' }} aria-hidden>
        {checked ? <Icon name="check" size={14} /> : null}
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
        <span style={{ fontSize: 12, color: checked ? 'var(--accent)' : 'var(--text-primary)' }}>{title}</span>
        <span style={{ fontSize: 11, lineHeight: 1.8, color: 'var(--text-muted)', whiteSpace: 'normal' }}>{desc}</span>
        {note && (
          <span style={{ fontSize: 11, lineHeight: 1.8, color: 'var(--warning)', whiteSpace: 'normal' }}>
            {note}
          </span>
        )}
        {hint && (
          <span style={{ fontSize: 11, lineHeight: 1.8, color: 'var(--text-muted)', whiteSpace: 'normal' }}>
            {hint}
          </span>
        )}
      </span>
    </button>
  )
}
