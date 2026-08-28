'use client'

import { useEffect, useRef, useState } from 'react'
import { useLang } from '@/components/LanguageToggle'
import { dirFor } from '@/lib/i18n'
import { guideStrings, type GuideHintId } from '@/app/guide/guide.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   P-GUIDE, phase 8 پ-۴ — the inline "؟" affordance.

   One source of text, two presentations: app/guide/guide.strings.ts holds
   both the /guide page's six sections AND this component's `hints` map, so a
   hint and the guide page can never drift apart the way a copy-pasted
   tooltip string would.

   This component is built and exported here but NOT wired into any existing
   page by this packet (AdminPanel.tsx and friends are senior-owned, and this
   file's own scope is exactly {page.tsx, guide.strings.ts, Hint.tsx, the
   test} — see the P-GUIDE handoff report for the exact file:line placement
   recommended for each of the 6 hint ids).

   Popover idiom copied from SmartModePopover.tsx (chat/components): own
   `open` state, outside-click via a rootRef, Escape closes, role="dialog",
   and `useKeepInViewport` corrects horizontal overflow after layout instead
   of trying to get a single CSS anchor right for every trigger position.
   ═══════════════════════════════════════════════════════════════════════════ */

type Props = {
  /** Must be one of GUIDE_HINT_IDS in guide.strings.ts — an id with no text
   *  there is a authoring bug, not a runtime state, so it renders the id
   *  itself rather than silently showing nothing (caught by
   *  guideContent.test.ts, not meant to reach production). */
  id: GuideHintId
  /** Rare escape hatch for a trigger that needs to sit flush against other
   *  inline controls (e.g. right next to a heading). Spacing only. */
  className?: string
}

export default function Hint({ id, className }: Props) {
  const lang = useLang()
  const s = guideStrings(lang)
  const rootRef = useRef<HTMLSpanElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)

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

  // Reposition after open so a trigger near a viewport edge doesn't clip the
  // popover — see useKeepInViewport's own header for why a plain CSS anchor
  // (inset-inline-start/-end) is not enough on its own.
  useEffect(() => {
    if (!open) return
    const el = popoverRef.current
    if (!el) return
    el.style.transform = ''
    const rect = el.getBoundingClientRect()
    const pad = 8
    let dx = 0
    if (rect.right > window.innerWidth - pad) dx = (window.innerWidth - pad) - rect.right
    if (rect.left + dx < pad) dx = pad - rect.left
    if (dx) el.style.transform = `translateX(${dx}px)`
  }, [open])

  const text = s.hints[id]

  return (
    <span
      ref={rootRef}
      className={className}
      dir={dirFor(lang)}
      style={{ position: 'relative', display: 'inline-flex', verticalAlign: 'middle' }}
    >
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={s.hintOpen}
        title={s.hintOpen}
        onClick={() => setOpen(o => !o)}
        style={{
          width: 16,
          height: 16,
          borderRadius: '50%',
          border: '1px solid var(--border)',
          background: open ? 'var(--accent-dim)' : 'transparent',
          color: open ? 'var(--accent)' : 'var(--text-muted)',
          fontSize: 10,
          lineHeight: 1,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          padding: 0,
          flexShrink: 0,
        }}
      >
        {s.hintButtonLabel}
      </button>

      {open && (
        <div
          ref={popoverRef}
          role="dialog"
          aria-label={s.hintOpen}
          className="card"
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            insetInlineStart: 0,
            zIndex: 30,
            width: 240,
            maxWidth: 'calc(100vw - 24px)',
            padding: '10px 12px',
            fontSize: 12,
            lineHeight: 1.8,
            color: 'var(--text-secondary)',
            boxShadow: 'var(--shadow-lg, 0 4px 16px rgba(0,0,0,0.2))',
          }}
        >
          {text}
        </div>
      )}
    </span>
  )
}
