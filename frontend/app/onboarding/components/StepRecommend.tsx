'use client'

import { Icon } from '@/components/ui/Icon'
import { Skeleton } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { formatPrice, formatContext } from '../onboardingHelpers'
import { stepRecommendStrings } from './StepRecommend.strings'
import { type Goal, type Recommendation } from '../types'

export function StepRecommend({
  activeGoal,
  recommendation,
  favoriteIds,
  catalogLoading,
  redirecting,
  onBack,
  onTips,
  onFinish,
}: {
  activeGoal: Goal
  recommendation: Recommendation
  favoriteIds: string[]
  catalogLoading: boolean
  redirecting: boolean
  onBack: () => void
  onTips: () => void
  onFinish: () => void
}) {
  const lang = useLang()
  const s = stepRecommendStrings(lang)
  const goalLabel = lang === 'fa' ? activeGoal.label_fa : activeGoal.label_en

  return (
    <div className="fade-in slide-up">
      <h2 className="text-2xl sm:text-3xl font-bold text-center mb-2">
        {s.titlePrefix}{goalLabel}{s.titleSuffix}
      </h2>
      <p className="text-center text-[var(--text-secondary)] mb-6">
        {favoriteIds.length > 0 ? s.subtitleWithFavorites : s.subtitleDefault}
      </p>

      <div className="card p-6 border-[var(--accent)]/40 bg-[var(--accent-dim)]/30">
        {catalogLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-7 w-1/2" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-[var(--accent)] flex items-center justify-center">
                <Icon name="models" size={24} className="text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xl font-bold">{recommendation.displayName}</div>
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  <span className="badge badge-accent">{recommendation.badgeLabel}</span>
                  {recommendation.fromCatalog ? (
                    <span className="badge badge-positive">{s.fromCatalog}</span>
                  ) : (
                    <span className="badge badge-warning">{s.defaultSuggestion}</span>
                  )}
                  {recommendation.id && favoriteIds.includes(recommendation.id) && (
                    <span className="badge badge-accent">{s.fromFavorites}</span>
                  )}
                </div>
              </div>
            </div>

            {recommendation.description && (
              <p className="text-sm text-[var(--text-secondary)] mt-4 leading-relaxed">
                {recommendation.description}
              </p>
            )}

            <div className="flex flex-wrap gap-2 mt-4">
              {recommendation.pricing && (
                <span className="badge bg-[var(--bg-elevated)] text-[var(--text-secondary)]">
                  {formatPrice(recommendation.pricing, lang)}
                </span>
              )}
              {recommendation.contextWindow && (
                <span className="badge bg-[var(--bg-elevated)] text-[var(--text-secondary)]">
                  {formatContext(recommendation.contextWindow, lang)} {s.contextSuffix}
                </span>
              )}
            </div>
          </>
        )}
      </div>

      <div className="flex items-center justify-between mt-8 gap-3">
        <button className="btn btn-ghost" onClick={onBack} disabled={catalogLoading}>
          <Icon name="arrowRight" size={16} />
          {s.back}
        </button>
        <div className="flex items-center gap-3">
          <button className="btn btn-secondary" onClick={onTips} disabled={catalogLoading}>
            {s.moreTips}
          </button>
          <button className="btn btn-primary btn-lg" onClick={onFinish} disabled={catalogLoading || redirecting}>
            {redirecting ? s.redirecting : s.startChat}
            <Icon name="send" size={18} />
          </button>
        </div>
      </div>
    </div>
  )
}
