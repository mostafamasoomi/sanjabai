'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { useCatalog } from '@/lib/useCatalog'
import { type ModelCatalogItem } from '@/types/catalog'
import { EmptyState, Skeleton } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { toFaDigits } from '@/lib/format'
import {
  ImageModelPicker,
  ImageCountPicker,
  ErrorPanel,
  GeneratingPanel,
  ResultGrid,
  buildErrorInfo,
  type ImagesErrorInfo,
  type ImagesResult,
} from './ImageGenPanels'
import { imageGenPanelsStrings } from './ImageGenPanels.strings'
import { imagesPageStrings } from './page.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   /images — POST /v1/images/generations against the live catalog.

   HONEST DEGRADATION IS THE POINT OF THIS PAGE, NOT A BUG IN IT: every image
   model in model_catalog is 'maintenance' with no price today (no upstream
   image credential works — see backend/images.py's module docstring and
   scripts/probe_media.py), so the filter below yields zero models right now
   and the empty state is what a correct visit looks like. Nothing here is
   hardcoded as a fallback model — see the three prior incidents (gpt-4o in
   the bot, mimo-v2.5 in tasks, tencent-hy3 in chat) this deliberately avoids
   repeating a fourth time.
   ═══════════════════════════════════════════════════════════════════════════ */

// Matches backend/images.py's MAX_N_IMAGES. The server clamps independently
// (`n_requested = min(n_requested, MAX_N_IMAGES)`), so this is only a UI
// bound for the stepper, not the enforcement point.
const MAX_N_IMAGES = 4

// Raw pixel dimensions — Latin digits always; localised for display via
// `sizeLabel` below, same rule as a model id or an API value.
const SIZE_VALUES = ['', '1024x1024', '1024x1792', '1792x1024']

/** `1024x1024` -> `۱۰۲۴×۱۰۲۴` (fa) / `1024×1024` (en). Not a plain number —
 *  a raw dimension string — so it goes through `toFaDigits` directly rather
 *  than `f.num`, but still must not stay Persian-digit in English mode. */
function sizeLabel(value: string, lang: 'fa' | 'en', defaultLabel: string): string {
  if (!value) return defaultLabel
  const pretty = value.replace('x', '×')
  return lang === 'en' ? pretty : toFaDigits(pretty)
}

type Status = 'idle' | 'generating' | 'success' | 'error'

function isImageModel(m: ModelCatalogItem): boolean {
  return !!m.modalities?.output?.includes('image') && m.availability === 'available'
}

export default function ImagesPage() {
  const lang = useLang()
  const f = fmt(lang)
  const s = imagesPageStrings(lang)
  const panelStrings = imageGenPanelsStrings(lang)
  const { token } = useAuth()
  const { models, loading: catalogLoading, error: catalogError } = useCatalog()

  const imageModels = useMemo(() => models.filter(isImageModel), [models])

  const [selected, setSelected] = useState<ModelCatalogItem | null>(null)
  const [prompt, setPrompt] = useState('')
  const [n, setN] = useState(1)
  const [size, setSize] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [result, setResult] = useState<ImagesResult | null>(null)
  const [errorInfo, setErrorInfo] = useState<ImagesErrorInfo | null>(null)

  // Default to the first available model once the (filtered) list arrives.
  // Never a hardcoded id — purely "first of whatever the live catalog says
  // is available right now".
  useEffect(() => {
    if (!selected && imageModels.length > 0) setSelected(imageModels[0])
    if (selected && !imageModels.find((m) => m.id === selected.id)) {
      setSelected(imageModels[0] ?? null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imageModels])

  const noModelsAvailable = !catalogLoading && !catalogError && imageModels.length === 0
  const formDisabled = catalogLoading || catalogError || noModelsAvailable || status === 'generating'
  const canSubmit = !formDisabled && !!selected && prompt.trim().length > 0

  const handleSubmit = async () => {
    if (!canSubmit || !selected) return
    setStatus('generating')
    setErrorInfo(null)
    setResult(null)

    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const body: Record<string, unknown> = {
      model: selected.providerModelId || selected.id,
      prompt: prompt.trim(),
      n,
    }
    if (size) body.size = size

    // No AbortController, no client timeout: a real generation on the one
    // route that ever reached a provider took 103s, and the backend allows
    // up to 300s (IMAGE_READ_TIMEOUT_SECONDS in backend/images.py). A
    // spinner that gives up early would silently break the feature.
    try {
      const res = await apiFetch('/v1/images/generations', {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      })

      let data: unknown = null
      try {
        data = await res.json()
      } catch {
        data = null
      }

      if (!res.ok) {
        setErrorInfo(buildErrorInfo(res.status, data, lang))
        setStatus('error')
        return
      }

      const d = (data ?? {}) as { data?: { url?: string; b64_json?: string }[]; billing?: { cost?: number } }
      const images = Array.isArray(d.data) ? d.data : []
      if (images.length === 0) {
        setErrorInfo({ message: s.noImagesReceived })
        setStatus('error')
        return
      }
      setResult({ images, cost: d.billing?.cost ?? null })
      setStatus('success')
    } catch {
      setErrorInfo({ message: s.networkError })
      setStatus('error')
    }
  }

  return (
    <div className="compare-page">
      <div className="compare-header">
        <div>
          <h1 className="page-title">{s.title}</h1>
          <p className="page-subtitle">{s.subtitle}</p>
        </div>
      </div>

      {catalogLoading && (
        <div className="card space-y-3">
          <Skeleton height="2.5rem" />
          <Skeleton height="6rem" />
        </div>
      )}

      {!catalogLoading && catalogError && (
        <EmptyState icon="warning" title={s.catalogErrorTitle} description={s.catalogErrorDesc} />
      )}

      {noModelsAvailable && (
        <EmptyState icon="camera" title={s.noModelsTitle} description={s.noModelsDesc} />
      )}

      {!catalogLoading && !catalogError && (
        <div className="card space-y-4">
          <div>
            <label className="compare-picker-label">{s.modelLabel}</label>
            <ImageModelPicker
              models={imageModels}
              selected={selected}
              onSelect={setSelected}
              disabled={formDisabled}
              s={panelStrings}
            />
          </div>

          <div>
            <label className="compare-picker-label">{s.promptLabel}</label>
            <textarea
              dir="auto"
              className="input w-full"
              rows={4}
              placeholder={s.promptPlaceholder}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              disabled={formDisabled}
            />
          </div>

          <div className="flex items-center gap-8 flex-wrap">
            <div>
              <label className="compare-picker-label">{s.countLabel(f.num(MAX_N_IMAGES))}</label>
              <ImageCountPicker value={n} onChange={setN} max={MAX_N_IMAGES} disabled={formDisabled} f={f} />
            </div>
            <div>
              <label className="compare-picker-label">{s.sizeLabel}</label>
              <select
                className="input"
                value={size}
                onChange={(e) => setSize(e.target.value)}
                disabled={formDisabled}
              >
                {SIZE_VALUES.map((value) => (
                  <option key={value} value={value}>
                    {sizeLabel(value, lang, s.sizeDefault)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <button className="btn btn-primary" onClick={handleSubmit} disabled={!canSubmit}>
            {s.submit}
          </button>
        </div>
      )}

      {status === 'generating' && <GeneratingPanel s={panelStrings} />}
      {status === 'error' && errorInfo && <ErrorPanel info={errorInfo} />}
      {status === 'success' && result && <ResultGrid result={result} f={f} s={panelStrings} />}
    </div>
  )
}
