'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { useCatalog } from '@/lib/useCatalog'
import { Skeleton } from '@/components/ui'
import { BrandLockup } from '@/components/BrandLockup'
import { useLang } from '@/components/LanguageToggle'
import { markOnboarded, isOnboarded, displayName } from '@/lib/onboarding'
import { onboardingPageStrings } from './page.strings'
import { GOALS } from './constants'
import { recommendFor, saveFavorites } from './onboardingHelpers'
import { useFavorites } from './hooks/useFavorites'
import { StepProgress } from './components/StepProgress'
import { StepWelcome } from './components/StepWelcome'
import { StepGoal } from './components/StepGoal'
import { StepModelSelect } from './components/StepModelSelect'
import { StepRecommend } from './components/StepRecommend'
import { StepTips } from './components/StepTips'

/* ═══════════════════════════════════════════════════════════════════════════
   Sanjabai Onboarding — Aurora v2
   A guided, premium first-time experience (Linear / Stripe style).

   Steps:
     0) Welcome      — greet the user by name
     1) Goal         — pick what they want to do (cards w/ icons)
     2) Model Select — browse catalog & pick 2-3 favorites
     3) Recommend    — suggest a model for that goal + "شروع چت"
     4) Tips         — quick wins (⌘K, change model, check balance) + finish

   Steps live as presentational components under ./components, goal/step data
   in ./constants, pure formatting/recommendation logic in ./onboardingHelpers,
   and favorites persistence in ./hooks/useFavorites — this file only owns
   step navigation, the auth/first-visit guard, and wiring it all together.
   ═══════════════════════════════════════════════════════════════════════════ */

export default function OnboardingPage() {
  const router = useRouter()
  const lang = useLang()
  const s = onboardingPageStrings(lang)
  const { user, loading: authLoading } = useAuth()
  const { models, loading: catalogLoading } = useCatalog()

  const [step, setStep] = useState(0)
  const [goalId, setGoalId] = useState<string | null>(null)
  const { favoriteIds, toggleFavorite } = useFavorites()
  const [redirecting, setRedirecting] = useState(false)

  const goal = GOALS.find((g) => g.id === goalId) || null
  const recommendation = goal ? recommendFor(goal, models, favoriteIds, lang) : null

  // ── First-visit / auth guards ────────────────────────────────────────────
  useEffect(() => {
    if (authLoading) return
    if (!user) {
      router.replace('/login')
      return
    }
    // Already completed onboarding → skip straight to the app.
    if (isOnboarded()) {
      router.replace('/chat')
    }
  }, [authLoading, user, router])

  const finish = useCallback(() => {
    saveFavorites(favoriteIds)
    markOnboarded()
    setRedirecting(true)
    router.replace('/chat')
  }, [router, favoriteIds])

  if (authLoading) {
    return (
      <div className="fixed inset-0 z-[200] overflow-y-auto bg-[var(--bg-base)] flex items-center justify-center p-4">
        <div className="w-full max-w-md space-y-4">
          <Skeleton className="h-8 w-2/3 mx-auto" />
          <Skeleton className="h-4 w-1/2 mx-auto" />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-6">
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
        </div>
      </div>
    )
  }

  if (!user) return null

  const activeGoal = GOALS.find((g) => g.id === goalId) || null

  return (
    <div className="fixed inset-0 z-[200] overflow-y-auto bg-[var(--bg-base)]">
      {/* Ambient premium glow */}
      <div
        className="pointer-events-none fixed inset-0 opacity-60"
        style={{
          background:
            'radial-gradient(60% 50% at 50% 0%, var(--accent-glow), transparent 70%)',
        }}
      />

      <div className="relative min-h-full flex flex-col">
        {/* ── Top bar: brand + step progress ───────────────────────────────── */}
        <div className="flex items-center justify-between px-5 sm:px-8 py-4 max-w-3xl w-full mx-auto">
          {/* The real lockup. This corner was still a rounded tile with the
              letter «M» in it -- a leftover mark from before the rebrand --
              next to "Sanjabai" set in the page font. */}
          <BrandLockup height={30} />
          <span className="badge badge-accent">{s.setupBadge}</span>
        </div>

        <StepProgress step={step} />

        {/* ── Content ─────────────────────────────────────────────────────── */}
        <div className="flex-1 flex items-center justify-center px-5 sm:px-8 py-6">
          <div className="w-full max-w-2xl">
            {step === 0 && (
              <StepWelcome userName={displayName(user.email)} onNext={() => setStep(1)} />
            )}

            {step === 1 && (
              <StepGoal
                goalId={goalId}
                onSelect={setGoalId}
                onBack={() => setStep(0)}
                onNext={() => setStep(2)}
              />
            )}

            {step === 2 && (
              <StepModelSelect
                models={models}
                catalogLoading={catalogLoading}
                favoriteIds={favoriteIds}
                onToggleFavorite={toggleFavorite}
                onBack={() => setStep(1)}
                onNext={() => setStep(3)}
              />
            )}

            {step === 3 && activeGoal && recommendation && (
              <StepRecommend
                activeGoal={activeGoal}
                recommendation={recommendation}
                favoriteIds={favoriteIds}
                catalogLoading={catalogLoading}
                redirecting={redirecting}
                onBack={() => setStep(2)}
                onTips={() => setStep(4)}
                onFinish={finish}
              />
            )}

            {step === 4 && (
              <StepTips redirecting={redirecting} onBack={() => setStep(3)} onFinish={finish} />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
