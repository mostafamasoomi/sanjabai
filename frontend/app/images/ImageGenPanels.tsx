'use client'

import Link from 'next/link'
import { type ModelCatalogItem } from '@/types/catalog'
import { Icon } from '@/components/ui/Icon'
import { Spinner } from '@/components/ui'
import type { Lang } from '@/components/LanguageToggle'
import { fmt, type Formatters } from '@/lib/i18n'
import { imageGenPanelsStrings } from './ImageGenPanels.strings'

type Strings = ReturnType<typeof imageGenPanelsStrings>

/* ═══════════════════════════════════════════════════════════════════════════
   Small presentational pieces for /images. Split out of page.tsx to keep
   both files well under the 500-line cap, not because these are reused
   anywhere else yet.
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Model picker ─────────────────────────────────────────────────────────
   Deliberately NOT the chat ModelPicker (app/chat/components/ModelPicker.tsx):
   that component persists the selection to the shared
   `sanjabai_selected_model` localStorage key, which the chat page reads back
   on load. An image model saved there would get silently restored as the
   *chat* model next visit and immediately 400 on /v1/chat/completions (image
   models are rejected there by design — see images.py's module docstring).
   This picker is a plain, page-local grid with no persistence. */
export function ImageModelPicker({
  models,
  selected,
  onSelect,
  disabled,
  s,
}: {
  models: ModelCatalogItem[]
  selected: ModelCatalogItem | null
  onSelect: (m: ModelCatalogItem) => void
  disabled?: boolean
  s: Strings
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" role="radiogroup" aria-label={s.pickerAriaLabel}>
      {models.map((m) => {
        const active = selected?.id === m.id
        return (
          <button
            key={m.id}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            onClick={() => onSelect(m)}
            className="card card-interactive text-start"
            style={{
              padding: 'var(--space-4)',
              borderColor: active ? 'var(--accent)' : undefined,
              boxShadow: active ? '0 0 0 3px var(--accent-dim)' : undefined,
              cursor: disabled ? 'not-allowed' : 'pointer',
              opacity: disabled ? 0.6 : 1,
            }}
          >
            <div className="flex items-center gap-2">
              <span className="card-icon">
                <Icon name="camera" size={16} />
              </span>
              <span className="card-title" style={{ fontSize: 'var(--fs-sm)' }}>
                {m.displayName}
              </span>
            </div>
            {m.description && (
              <p className="card-desc" style={{ marginTop: '0.5rem' }}>
                {m.description}
              </p>
            )}
          </button>
        )
      })}
    </div>
  )
}

/* ── Count stepper (n, capped at MAX_N_IMAGES = 4 in backend/images.py) ──── */
export function ImageCountPicker({
  value,
  onChange,
  max,
  disabled,
  f,
}: {
  value: number
  onChange: (n: number) => void
  max: number
  disabled?: boolean
  f: Formatters
}) {
  const options = Array.from({ length: max }, (_, i) => i + 1)
  return (
    <div className="flex items-center gap-2">
      {options.map((n) => (
        <button
          key={n}
          type="button"
          disabled={disabled}
          onClick={() => onChange(n)}
          className={`btn btn-sm ${value === n ? 'btn-primary' : 'btn-secondary'}`}
        >
          {f.num(n)}
        </button>
      ))}
    </div>
  )
}

/* ── Error info + panel ───────────────────────────────────────────────────
   Message text always prefers the server's own string (`error.message` /
   `detail`) so the page can never say something images.py itself does not
   also say — the fallback strings below are copy-pasted verbatim from
   images.py only as a safety net for a response the backend never actually
   sends (e.g. a raw upstream body forwarded through untouched). */
export type ImagesErrorInfo = {
  message: string
  actionLabel?: string
  actionHref?: string
}

export function buildErrorInfo(status: number, body: unknown, lang: Lang): ImagesErrorInfo {
  const s = imageGenPanelsStrings(lang)
  const b = (body ?? {}) as {
    error?: { message?: string; code?: string }
    detail?: string
    code?: string
  }
  const code = b.error?.code || b.code
  // Server message (error.message / detail) is backend-sourced Persian and
  // is rendered verbatim in both languages — see the file header comment.
  const serverMessage = b.error?.message || b.detail

  if (status === 401) {
    return { message: serverMessage || s.loginPrompt, actionLabel: s.loginAction, actionHref: '/login' }
  }
  if (code === 'balance' || status === 429) {
    return {
      message: serverMessage || s.insufficientBalance,
      actionLabel: s.topUpAction,
      actionHref: '/wallet',
    }
  }
  if (code === 'model_not_available') {
    return { message: serverMessage || s.modelNotAvailable }
  }
  if (code === 'price_not_set') {
    return { message: serverMessage || s.priceNotSet }
  }
  if (code === 'no_images') {
    return { message: serverMessage || s.noImages }
  }
  if (code === 'model_required') {
    return { message: serverMessage || s.modelRequired }
  }
  return { message: serverMessage || s.serviceUnavailable(String(status)) }
}

export function ErrorPanel({ info }: { info: ImagesErrorInfo }) {
  return (
    <div
      className="card"
      style={{ borderColor: 'var(--danger)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}
    >
      <div className="flex items-center gap-3">
        <span className="card-icon" style={{ background: 'var(--danger-dim)', color: 'var(--danger)' }}>
          <Icon name="warning" size={16} />
        </span>
        <p className="card-desc" style={{ color: 'var(--text-primary)' }}>{info.message}</p>
      </div>
      {info.actionHref && info.actionLabel && (
        <Link href={info.actionHref} className="btn btn-secondary btn-sm">
          {info.actionLabel}
        </Link>
      )}
    </div>
  )
}

/* ── In-progress state ─────────────────────────────────────────────────────
   THE headline trap this page must not fall into: a real generation took
   103s on the one route that ever reached a provider, and the backend
   allows up to 300s. No spinner here ever auto-gives-up. */
export function GeneratingPanel({ s }: { s: Strings }) {
  return (
    <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
      <Spinner size="sm" />
      <p className="card-desc" style={{ color: 'var(--text-primary)' }}>{s.generating}</p>
    </div>
  )
}

/* ── Result grid ──────────────────────────────────────────────────────────
   Renders both documented OpenAI images response shapes -- {url} or
   {b64_json} -- exactly the two the backend's _extract_images() accepts. */
export type ImagesResult = {
  images: { url?: string; b64_json?: string }[]
  cost: number | null
}

export function ResultGrid({ result, f, s }: { result: ImagesResult; f: Formatters; s: Strings }) {
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {result.images.map((img, i) => {
          const src = img.url || (img.b64_json ? `data:image/png;base64,${img.b64_json}` : '')
          if (!src) return null
          return (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={i}
              src={src}
              alt={s.generatedImageAlt(f.num(i + 1))}
              style={{ width: '100%', height: 'auto', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}
            />
          )
        })}
      </div>
      {result.cost != null && <p className="card-meta">{s.requestCost(f.price(result.cost))}</p>}
    </div>
  )
}
