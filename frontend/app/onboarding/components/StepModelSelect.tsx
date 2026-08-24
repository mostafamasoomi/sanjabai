import { priceBand, PRICE_BAND_LABEL } from '@/lib/useCatalog'
import { type ModelCatalogItem } from '@/types/catalog'
import { Icon } from '@/components/ui/Icon'
import { Skeleton } from '@/components/ui'
import { faNum } from '@/lib/format'
import { formatPriceShort, formatContext } from '../onboardingHelpers'

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
  return (
    <div className="fade-in slide-up">
      <h2 className="text-2xl sm:text-3xl font-bold text-center mb-2">مدل‌های موردعلاقه شما</h2>
      <p className="text-center text-[var(--text-secondary)] mb-6">
        از بین مدل‌های موجود، ۲ تا ۳ مدل موردعلاقه‌تان را انتخاب کنید.
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
          <p className="text-[var(--text-secondary)]">در حال حاضر مدلی در دسترس نیست.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[45vh] overflow-y-auto pr-1">
          {models.map((m) => {
            const selected = favoriteIds.includes(m.id)
            return (
              <button
                key={m.id}
                onClick={() => onToggleFavorite(m.id)}
                className={`card card-interactive text-right flex items-start gap-3 p-4 cursor-pointer transition-all ${
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
                    <span className="badge badge-accent text-[10px] shrink-0">{PRICE_BAND_LABEL[priceBand(m, models)]}</span>
                  </div>
                  <div className="text-xs text-[var(--text-muted)] mt-1">
                    {formatPriceShort(m.pricing)}
                  </div>
                  <div className="text-[11px] text-[var(--text-muted)] mt-0.5">
                    {formatContext(m.contextWindow)}
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
          {faNum(favoriteIds.length)} مدل انتخاب شده
        </p>
      )}

      <div className="flex items-center justify-between mt-8 gap-3">
        <button className="btn btn-ghost" onClick={onBack}>
          <Icon name="arrowRight" size={16} />
          قبلی
        </button>
        <button
          className="btn btn-primary btn-lg"
          onClick={onNext}
        >
          ادامه
          <Icon name="arrowLeft" size={18} />
        </button>
      </div>
    </div>
  )
}
