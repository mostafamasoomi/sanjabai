'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { useCatalog } from '@/lib/useCatalog'
import { type ModelCatalogItem } from '@/types/catalog'
import { EmptyState, Skeleton } from '@/components/ui'
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

const SIZE_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'پیش‌فرض' },
  { value: '1024x1024', label: '۱۰۲۴×۱۰۲۴' },
  { value: '1024x1792', label: '۱۰۲۴×۱۷۹۲' },
  { value: '1792x1024', label: '۱۷۹۲×۱۰۲۴' },
]

type Status = 'idle' | 'generating' | 'success' | 'error'

function isImageModel(m: ModelCatalogItem): boolean {
  return !!m.modalities?.output?.includes('image') && m.availability === 'available'
}

export default function ImagesPage() {
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
        setErrorInfo(buildErrorInfo(res.status, data))
        setStatus('error')
        return
      }

      const d = (data ?? {}) as { data?: { url?: string; b64_json?: string }[]; billing?: { cost?: number } }
      const images = Array.isArray(d.data) ? d.data : []
      if (images.length === 0) {
        setErrorInfo({ message: 'تولید تصویر ناموفق بود؛ هیچ تصویری از سرویس دریافت نشد' })
        setStatus('error')
        return
      }
      setResult({ images, cost: d.billing?.cost ?? null })
      setStatus('success')
    } catch {
      setErrorInfo({ message: 'خطا در ارتباط با سرور. اتصال اینترنت خود را بررسی کنید و دوباره تلاش کنید.' })
      setStatus('error')
    }
  }

  return (
    <div className="compare-page">
      <div className="compare-header">
        <div>
          <h1 className="page-title">تولید تصویر</h1>
          <p className="page-subtitle">توضیح متنی خود را بنویسید و از یک مدل تولید تصویر فعال، تصویر بسازید</p>
        </div>
      </div>

      {catalogLoading && (
        <div className="card space-y-3">
          <Skeleton height="2.5rem" />
          <Skeleton height="6rem" />
        </div>
      )}

      {!catalogLoading && catalogError && (
        <EmptyState
          icon="warning"
          title="خطا در دریافت فهرست مدل‌ها"
          description="اتصال به سرور برقرار نشد. لطفاً صفحه را دوباره بارگذاری کنید."
        />
      )}

      {noModelsAvailable && (
        <EmptyState
          icon="camera"
          title="در حال حاضر هیچ مدل تولید تصویری فعال نیست"
          description="مدل‌های تولید تصویر پس از تأیید با پروب زنده و ثبت قیمت، اینجا نمایش داده می‌شوند."
        />
      )}

      {!catalogLoading && !catalogError && (
        <div className="card space-y-4">
          <div>
            <label className="compare-picker-label">مدل</label>
            <ImageModelPicker models={imageModels} selected={selected} onSelect={setSelected} disabled={formDisabled} />
          </div>

          <div>
            <label className="compare-picker-label">توضیح تصویر</label>
            <textarea
              dir="auto"
              className="input w-full"
              rows={4}
              placeholder="مثلاً: یک منظره کوهستانی در غروب آفتاب"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              disabled={formDisabled}
            />
          </div>

          <div className="flex items-center gap-8 flex-wrap">
            <div>
              <label className="compare-picker-label">تعداد تصویر (حداکثر ۴)</label>
              <ImageCountPicker value={n} onChange={setN} max={MAX_N_IMAGES} disabled={formDisabled} />
            </div>
            <div>
              <label className="compare-picker-label">اندازه تصویر</label>
              <select
                className="input"
                value={size}
                onChange={(e) => setSize(e.target.value)}
                disabled={formDisabled}
              >
                {SIZE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <button className="btn btn-primary" onClick={handleSubmit} disabled={!canSubmit}>
            تولید تصویر
          </button>
        </div>
      )}

      {status === 'generating' && <GeneratingPanel />}
      {status === 'error' && errorInfo && <ErrorPanel info={errorInfo} />}
      {status === 'success' && result && <ResultGrid result={result} />}
    </div>
  )
}
