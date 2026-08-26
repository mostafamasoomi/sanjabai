'use client'

/**
 * The one and only place a full API key secret is ever shown to the user —
 * right after `POST /api-keys` (creation) or `POST /api-keys/{id}/rotate`.
 * Neither the key list nor any other UI may render or reconstruct a full
 * key: the backend only ever stores a hash and returns the raw secret in
 * this single response, so this modal is the last chance for the user to
 * see and copy it.
 *
 * Deliberately hard to dismiss by accident:
 *   - no backdrop-click-to-close (the backdrop has no click handler at all)
 *   - no "x" close button
 *   - the only way out is the explicit "کلید را ذخیره کردم" acknowledgement
 *
 * Copy has a fallback: `navigator.clipboard` can throw or simply not exist
 * (insecure origin, some in-app browsers, permission denied). The raw key
 * is always rendered in a read-only, click-to-select input regardless of
 * whether the clipboard write succeeded, so a failed copy never loses the
 * key — the user can still select-and-copy manually.
 */

import { useRef, useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { apiKeyRevealModalStrings } from './ApiKeyRevealModal.strings'

type ApiKeyRevealModalProps = {
  open: boolean
  rawKey: string | null
  /** True when this reveal follows a rotation rather than a fresh creation
   * — shows the extra warning that the previous secret stopped working. */
  isRotation?: boolean
  onAcknowledge: () => void
}

export function ApiKeyRevealModal({ open, rawKey, isRotation, onAcknowledge }: ApiKeyRevealModalProps) {
  const lang = useLang()
  const s = apiKeyRevealModalStrings(lang)
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')
  const inputRef = useRef<HTMLInputElement>(null)

  if (!open || !rawKey) return null

  const selectKey = () => {
    inputRef.current?.select()
  }

  const copyKey = async () => {
    try {
      if (!navigator.clipboard) throw new Error('clipboard-unavailable')
      await navigator.clipboard.writeText(rawKey)
      setCopyState('copied')
      setTimeout(() => setCopyState('idle'), 2500)
    } catch {
      // Clipboard write failed or is unavailable on this origin/browser —
      // fall back to selecting the text so the user can copy manually.
      // The key is never lost: it stays visible and selectable either way.
      selectKey()
      setCopyState('failed')
      setTimeout(() => setCopyState('idle'), 4000)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="apikey-reveal-title"
    >
      {/* Backdrop — intentionally no onClick: clicking it must not close the modal. */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />

      <div className="relative bg-[var(--bg-elev)] border border-[var(--border-strong)] rounded-[var(--radius-xl)] p-6 max-w-lg w-full shadow-[var(--shadow-lg)] fade-in">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Icon name="check" size={18} className="text-positive" />
          <h2 id="apikey-reveal-title" style={{ fontSize: 16, fontWeight: 700, color: 'var(--positive)' }}>
            {isRotation ? s.rotated : s.created}
          </h2>
        </div>

        <div style={{
          display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 14,
          padding: '10px 12px', borderRadius: 10,
          background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.25)',
        }}>
          <Icon name="warning" size={16} className="text-danger" style={{ marginTop: 2, flexShrink: 0 }} />
          <p style={{ fontSize: 13, color: 'var(--danger)', margin: 0, lineHeight: 1.7 }}>
            {s.warning}
            {isRotation && s.rotationWarningSuffix}
          </p>
        </div>

        <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>
          {s.apiKeyLabel}
        </label>
        <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
          <input
            ref={inputRef}
            readOnly
            value={rawKey}
            onClick={selectKey}
            onFocus={selectKey}
            spellCheck={false}
            className="input flex-1"
            style={{
              direction: 'ltr', textAlign: 'left', fontFamily: 'var(--font-mono)',
              fontSize: 13, cursor: 'text',
            }}
          />
          <button
            onClick={copyKey}
            type="button"
            className="btn btn-secondary btn-sm"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexShrink: 0 }}
          >
            <Icon name={copyState === 'copied' ? 'check' : 'copy'} size={14} />
            {copyState === 'copied' ? s.copied : s.copy}
          </button>
        </div>

        {copyState === 'failed' && (
          <p style={{ fontSize: 12, color: 'var(--danger)', marginBottom: 12 }}>
            {s.copyFailed}
          </p>
        )}
        {copyState !== 'failed' && (
          <p style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 12 }}>
            {s.copyHint}
          </p>
        )}

        <button
          onClick={onAcknowledge}
          type="button"
          className="btn btn-primary"
          style={{ width: '100%', justifyContent: 'center', marginTop: 4 }}
        >
          {s.acknowledge}
        </button>
      </div>
    </div>
  )
}
