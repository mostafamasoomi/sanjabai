'use client'

import { priceBand } from '@/lib/useCatalog'
import { type ModelCatalogItem } from '@/types/catalog'
import { Icon } from '@/components/ui/Icon'
import { Skeleton } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt, navIcon } from '@/lib/i18n'
import { formatPriceShort, formatContext } from '../onboardingHelpers'
import { onboardingHelpersStrings } from '../onboardingHelpers.strings'
import { stepModelSelectStrings } from './StepModelSelect.strings'

export function StepModelSelect({
  models,
  catalogLoading,
  favoriteIds,
  onToggleFavorite,
  onBack,
  onNext,
}: {
  models: ModelCatalogItem[]
  catalogLoading: boolean
  favoriteIds: string[]
  onToggleFavorite: (id: string) => void
  onBack: () => void
  onNext: () => void
}) {
  const lang = useLang()
  const s = stepModelSelectStrings(lang)
  const f = fmt(lang)
  // lib/useCatalog's own PRICE_BAND_LABEL is Persian-only (out of this
  // batch's scope) -- see onboardingHelpers.strings.ts's file comment.
  const priceBandLabel = onboardingHelpersStrings(lang).priceBand

  return (
    <div className="fade-in slide-up">
      <h2 className="text-2xl sm:text-3xl font-bold text-center mb-2">{s.title}</h2>
      <p className="text-center text-[var(--text-secondary)] mb-6">
        {s.subtitle}
      </p>

      {catalogLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card p-4">
              <Skeleton className="h-5 w-2/3 mb-2" />
              <Skeleton className="h-4 w-1/3 mb-3" />
              <Skeleton className="h-3 w-full" />
            </div>
          ))}
        </div>
      ) : models.length === 0 ? (
        <div className="text-center py-12">
          <Icon name="models" size={40} className="text-[var(--text-muted)] mx-auto mb-3" />
          <p className="text-[var(--text-secondary)]">{s.noModels}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[45vh] overflow-y-auto pr-1">
          {models.map((m) => {
            const selected = favoriteIds.includes(m.id)
            return (
              <button
                key={m.id}
                onClick={() => onToggleFavorite(m.id)}
                className={`card card-interactive text-start flex items-start gap-3 p-4 cursor-pointer transition-all ${
                  selected
                    ? 'border-[var(--accent)] bg-[var(--accent-dim)] shadow-[var(--shadow-glow)]'
                    : ''
                }`}
              >
                <div
                  className={`shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-colors ${
                    selected
                      ? 'bg-[var(--accent)] text-white'
                      : 'bg-[var(--bg-elevated)] text-[var(--accent)]'
                  }`}
                >
                  <Icon name="models" size={20} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm truncate">{m.displayName}</span>
                    <span className="badge badge-accent text-[10px] shrink-0">{priceBandLabel[priceBand(m, models)]}</span>
                  </div>
                  <div className="text-xs text-[var(--text-muted)] mt-1">
                    {formatPriceShort(m.pricing, lang)}
                  </div>
                  <div className="text-[11px] text-[var(--text-muted)] mt-0.5">
                    {formatContext(m.contextWindow, lang)}
                  </div>
                </div>
                {selected && (
                  <Icon name="check" size={18} className="text-[var(--accent)] shrink-0 mt-1" />
                )}
              </button>
            )
          })}
        </div>
      )}

      {favoriteIds.length > 0 && (
        <p className="text-center text-xs text-[var(--accent)] mt-3">
          {s.selectedCount(f.num(favoriteIds.length))}
        </p>
      )}

      <div className="flex items-center justify-between mt-8 gap-3">
        <button className="btn btn-ghost" onClick={onBack}>
          <Icon name={navIcon(lang, 'back')} size={16} />
          {s.back}
        </button>
        <button
          className="btn btn-primary btn-lg"
          onClick={onNext}
        >
          {s.next}
          <Icon name={navIcon(lang, 'forward')} size={18} />
        </button>
      </div>
    </div>
  )
}
