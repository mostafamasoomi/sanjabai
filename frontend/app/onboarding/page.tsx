'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { useCatalog } from '@/lib/useCatalog'
import { type ModelCatalogItem, type Currency } from '@/types/catalog'
import { Icon, type IconName } from '@/components/ui/Icon'
import { Skeleton } from '@/components/ui'
import { faNum, faCompact } from '@/lib/format'
import { markOnboarded, isOnboarded, displayName } from '@/lib/onboarding'

/* ═══════════════════════════════════════════════════════════════════════════
   Sanjabai Onboarding — Aurora v2
   A guided, premium first-time experience (Linear / Stripe style).

   Steps:
     0) Welcome      — greet the user by name
     1) Goal         — pick what they want to do (cards w/ icons)
     2) Model Select — browse catalog & pick 2-3 favorites
     3) Recommend    — suggest a model for that goal + "شروع چت"
     4) Tips         — quick wins (⌘K, change model, check balance) + finish
   ═══════════════════════════════════════════════════════════════════════════ */

type Goal = {
  id: string
  label: string
  icon: IconName
  hint: string
  /** keywords matched against catalog capabilities / recommendedFor */
  keywords: string[]
  /** used only when the live catalog is unavailable */
  fallbackModel: string
  fallbackProvider: string
}

const GOALS: Goal[] = [
  {
    id: 'coding',
    label: 'کدنویسی',
    icon: 'code',
    hint: 'تولید، دیباگ و بازنویسی کد',
    keywords: ['code', 'coding', 'developer', 'programming'],
    fallbackModel: 'Claude Sonnet 4',
    fallbackProvider: 'Anthropic',
  },
  {
    id: 'writing',
    label: 'نوشتن',
    icon: 'chat',
    hint: 'محتوا، متن و ایدهپردازی',
    keywords: ['writing', 'creative', 'content', 'copy'],
    fallbackModel: 'GPT-4o',
    fallbackProvider: 'OpenAI',
  },
  {
    id: 'translation',
    label: 'ترجمه',
    icon: 'search',
    hint: 'ترجمه روان چندزبانه',
    keywords: ['translation', 'translate', 'multilingual', 'language'],
    fallbackModel: 'Gemini 1.5 Pro',
    fallbackProvider: 'Google',
  },
  {
    id: 'analysis',
    label: 'تحلیل',
    icon: 'dashboard',
    hint: 'داده، منطق و استنتاج',
    keywords: ['analysis', 'reasoning', 'data', 'research'],
    fallbackModel: 'OpenAI o1',
    fallbackProvider: 'OpenAI',
  },
  {
    id: 'general',
    label: 'چت عمومی',
    icon: 'models',
    hint: 'گفتگوی آزاد و پرسوجو',
    keywords: ['chat', 'general', 'conversation', 'assistant'],
    fallbackModel: 'GPT-4o mini',
    fallbackProvider: 'OpenAI',
  },
]

const STEP_LABELS = ['خوشآمد', 'هدف شما', 'انتخاب مدل', 'مدل پیشنهادی', 'نکات سریع']

type Recommendation = {
  displayName: string
  provider: string
  description?: string
  pricing?: ModelCatalogItem['pricing']
  contextWindow?: number
  fromCatalog: boolean
  id?: string
}

function recommendFor(goal: Goal, models: ModelCatalogItem[], favoriteIds: string[]): Recommendation {
  const kw = goal.keywords
  // First try to find a matching model among favorites
  const favorites = models.filter((m) => favoriteIds.includes(m.id))
  const matchInFavorites = favorites.find((m) => {
    const caps = (m.capabilities || []).map((c) => c.toLowerCase())
    const rec = (m.recommendedFor || []).map((r) => r.toLowerCase())
    return kw.some((k) => caps.some((c) => c.includes(k)) || rec.some((r) => r.includes(k)))
  })
  const match = matchInFavorites || models.find((m) => {
    const caps = (m.capabilities || []).map((c) => c.toLowerCase())
    const rec = (m.recommendedFor || []).map((r) => r.toLowerCase())
    return kw.some((k) => caps.some((c) => c.includes(k)) || rec.some((r) => r.includes(k)))
  })
  if (match) {
    return {
      displayName: match.displayName,
      provider: match.provider,
      description: match.description,
      pricing: match.pricing,
      contextWindow: match.contextWindow,
      fromCatalog: true,
      id: match.id,
    }
  }
  return {
    displayName: goal.fallbackModel,
    provider: goal.fallbackProvider,
    fromCatalog: false,
  }
}

function formatPrice(p?: ModelCatalogItem['pricing']): string {
  if (!p) return ''
  const cur = p.currency === 'IRT' ? 'تومان' : p.currency === 'IRR' ? 'ریال' : p.currency
  return `هر ۱ میلیون توکن — ورودی ${p.inputPerMillion} · خروجی ${p.outputPerMillion} ${cur}`
}

function formatPriceShort(p?: ModelCatalogItem['pricing']): string {
  if (!p) return ''
  const cur = p.currency === 'IRT' ? 'تومان' : p.currency === 'IRR' ? 'ریال' : p.currency
  const fmt = faNum
  return `ورودی ${fmt(p.inputPerMillion)} · خروجی ${fmt(p.outputPerMillion)} ${cur}`
}

function formatContext(n?: number): string {
  if (!n) return ''
  // `M` / `K` are Latin runs: in an RTL paragraph they were placed before
  // the number they abbreviate. Persian words carry the same meaning safely.
  return `${faCompact(n)} توکن`
}

const FAVORITES_KEY = 'sanjabai_favorite_models'

function loadFavorites(): string[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = localStorage.getItem(FAVORITES_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveFavorites(ids: string[]) {
  try {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify(ids))
  } catch {
    // ignore
  }
}

export default function OnboardingPage() {
  const router = useRouter()
  const { user, loading: authLoading } = useAuth()
  const { models, loading: catalogLoading } = useCatalog()

  const [step, setStep] = useState(0)
  const [goalId, setGoalId] = useState<string | null>(null)
  const [favoriteIds, setFavoriteIds] = useState<string[]>([])
  const [redirecting, setRedirecting] = useState(false)

  const goal = GOALS.find((g) => g.id === goalId) || null
  const recommendation = goal ? recommendFor(goal, models, favoriteIds) : null

  // Load saved favorites on mount
  useEffect(() => {
    setFavoriteIds(loadFavorites())
  }, [])

  // Persist favorites whenever they change
  useEffect(() => {
    if (favoriteIds.length > 0) {
      saveFavorites(favoriteIds)
    }
  }, [favoriteIds])

  const toggleFavorite = useCallback((id: string) => {
    setFavoriteIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id)
      return [...prev, id]
    })
  }, [])

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
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-[var(--accent)] flex items-center justify-center">
              <span className="text-white text-sm font-bold">M</span>
            </div>
            <span className="text-base font-bold text-gradient tracking-tight">Sanjabai</span>
          </div>
          <span className="badge badge-accent">تنظیمات اولیه</span>
        </div>

        {/* Step indicator */}
        <div className="max-w-3xl w-full mx-auto px-5 sm:px-8 pb-2">
          <div className="flex items-center gap-2">
            {STEP_LABELS.map((label, i) => {
              const done = i < step
              const current = i === step
              return (
                <div key={label} className="flex-1">
                  <div className="h-1 rounded-full overflow-hidden bg-[var(--bg-elevated)]">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: done || current ? '100%' : '0%',
                        background: current
                          ? 'linear-gradient(90deg, var(--accent), var(--accent-hover))'
                          : 'var(--accent)',
                      }}
                    />
                  </div>
                  <div
                    className={`text-[11px] mt-1.5 ${
                      current
                        ? 'text-[var(--accent)] font-medium'
                        : done
                        ? 'text-[var(--text-secondary)]'
                        : 'text-[var(--text-muted)]'
                    }`}
                  >
                    {label}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* ── Content ─────────────────────────────────────────────────────── */}
        <div className="flex-1 flex items-center justify-center px-5 sm:px-8 py-6">
          <div className="w-full max-w-2xl">
            {/* STEP 0 — Welcome */}
            {step === 0 && (
              <div className="text-center fade-in slide-up">
                <div className="mx-auto w-16 h-16 rounded-2xl bg-[var(--accent-dim)] flex items-center justify-center mb-6">
                  <Icon name="sparkles" size={32} className="text-[var(--accent)]" />
                </div>
                <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
                  {displayName(user.email) ? (
                    <>
                      خوش آمدید، <span className="text-gradient">{displayName(user.email)}</span>
                    </>
                  ) : (
                    <>
                      به <span className="text-gradient">Sanjabai</span> خوش آمدید
                    </>
                  )}
                </h1>
                <p className="text-[var(--text-secondary)] mt-3 max-w-md mx-auto leading-relaxed">
                  چند ثانیه وقت بدهید تا همهچیز را برای شما آماده کنیم. فقط چند قدم ساده تا شروع چت با
                  بهترین مدل‌های هوش مصنوعی دنیا.
                </p>
                <button className="btn btn-primary btn-lg mt-8" onClick={() => setStep(1)}>
                  بیا شروع کنیم
                  <Icon name="arrowLeft" size={18} />
                </button>
              </div>
            )}

            {/* STEP 1 — Goal selection */}
            {step === 1 && (
              <div className="fade-in slide-up">
                <h2 className="text-2xl sm:text-3xl font-bold text-center mb-2">قصد دارید چه کاری کنید؟</h2>
                <p className="text-center text-[var(--text-secondary)] mb-6">
                  بر اساس انتخاب شما، بهترین مدل را پیشنهاد می‌دهیم.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {GOALS.map((g, idx) => {
                    const selected = g.id === goalId
                    return (
                      <button
                        key={g.id}
                        onClick={() => setGoalId(g.id)}
                        className={`card card-interactive text-right flex items-center gap-4 p-4 cursor-pointer transition-all slide-up ${
                          selected
                            ? 'border-[var(--accent)] bg-[var(--accent-dim)] shadow-[var(--shadow-glow)]'
                            : ''
                        }`}
                        style={{ animationDelay: `${0.05 + idx * 0.05}s` }}
                      >
                        <div
                          className={`shrink-0 w-12 h-12 rounded-xl flex items-center justify-center transition-colors ${
                            selected
                              ? 'bg-[var(--accent)] text-white'
                              : 'bg-[var(--bg-elevated)] text-[var(--accent)]'
                          }`}
                        >
                          <Icon name={g.icon} size={24} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-semibold text-base">{g.label}</div>
                          <div className="text-xs text-[var(--text-muted)] mt-0.5">{g.hint}</div>
                        </div>
                        {selected && (
                          <Icon name="check" size={20} className="text-[var(--accent)] shrink-0" />
                        )}
                      </button>
                    )
                  })}
                </div>
                <div className="flex items-center justify-between mt-8 gap-3">
                  <button className="btn btn-ghost" onClick={() => setStep(0)}>
                    <Icon name="arrowRight" size={16} />
                    قبلی
                  </button>
                  <button
                    className="btn btn-primary btn-lg"
                    disabled={!goalId}
                    onClick={() => setStep(2)}
                  >
                    ادامه
                    <Icon name="arrowLeft" size={18} />
                  </button>
                </div>
              </div>
            )}

            {/* STEP 2 — Model selection (browse catalog & pick favorites) */}
            {step === 2 && (
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
                    {models.map((m, idx) => {
                      const selected = favoriteIds.includes(m.id)
                      return (
                        <button
                          key={m.id}
                          onClick={() => toggleFavorite(m.id)}
                          className={`card card-interactive text-right flex items-start gap-3 p-4 cursor-pointer transition-all slide-up ${
                            selected
                              ? 'border-[var(--accent)] bg-[var(--accent-dim)] shadow-[var(--shadow-glow)]'
                              : ''
                          }`}
                          style={{ animationDelay: `${0.05 + Math.min(idx, 10) * 0.03}s` }}
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
                              <span className="badge badge-accent text-[10px] shrink-0">{m.provider}</span>
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
                  <button className="btn btn-ghost" onClick={() => setStep(1)}>
                    <Icon name="arrowRight" size={16} />
                    قبلی
                  </button>
                  <button
                    className="btn btn-primary btn-lg"
                    onClick={() => setStep(3)}
                  >
                    ادامه
                    <Icon name="arrowLeft" size={18} />
                  </button>
                </div>
              </div>
            )}

            {/* STEP 3 — Recommendation */}
            {step === 3 && activeGoal && recommendation && (
              <div className="fade-in slide-up">
                <h2 className="text-2xl sm:text-3xl font-bold text-center mb-2">
                  مدل پیشنهادی برای «{activeGoal.label}»
                </h2>
                <p className="text-center text-[var(--text-secondary)] mb-6">
                  {favoriteIds.length > 0
                    ? 'بر اساس مدل‌های موردعلاقه و هدف شما، این مدل پیشنهاد می‌شود.'
                    : 'این مدل برای نیاز شما بهینه شده — هر وقت خواستید می‌توانید عوضش کنید.'}
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
                            <span className="badge badge-accent">{recommendation.provider}</span>
                            {recommendation.fromCatalog ? (
                              <span className="badge badge-positive">از کاتالوگ زنده</span>
                            ) : (
                              <span className="badge badge-warning">پیشنهاد پیشفرض</span>
                            )}
                            {recommendation.id && favoriteIds.includes(recommendation.id) && (
                              <span className="badge badge-accent">از علاقه‌مندی‌ها</span>
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
                            {formatPrice(recommendation.pricing)}
                          </span>
                        )}
                        {recommendation.contextWindow && (
                          <span className="badge bg-[var(--bg-elevated)] text-[var(--text-secondary)]">
                            {formatContext(recommendation.contextWindow)} contexts
                          </span>
                        )}
                      </div>
                    </>
                  )}
                </div>

                <div className="flex items-center justify-between mt-8 gap-3">
                  <button className="btn btn-ghost" onClick={() => setStep(2)} disabled={catalogLoading}>
                    <Icon name="arrowRight" size={16} />
                    قبلی
                  </button>
                  <div className="flex items-center gap-3">
                    <button className="btn btn-secondary" onClick={() => setStep(4)} disabled={catalogLoading}>
                      نکات بعدی
                    </button>
                    <button className="btn btn-primary btn-lg" onClick={finish} disabled={catalogLoading || redirecting}>
                      {redirecting ? 'در حال انتقال...' : 'شروع چت'}
                      <Icon name="send" size={18} />
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* STEP 4 — Quick tips */}
            {step === 4 && (
              <div className="fade-in slide-up">
                <h2 className="text-2xl sm:text-3xl font-bold text-center mb-2">سه نکته که کار را راه میاندازد</h2>
                <p className="text-center text-[var(--text-secondary)] mb-6">
                  چند ثانیه دیگر و آماده میکارید.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="card p-5 slide-up" style={{ animationDelay: '0.05s' }}>
                    <div className="w-11 h-11 rounded-xl bg-[var(--bg-elevated)] flex items-center justify-center mb-3">
                      <Icon name="search" size={22} className="text-[var(--accent)]" />
                    </div>
                    <div className="font-semibold mb-1">منوی سریع</div>
                    <p className="text-xs text-[var(--text-muted)] leading-relaxed">
                      با زدن{' '}
                      <kbd className="text-[11px] bg-[var(--bg-surface)] px-1.5 py-0.5 rounded border border-[var(--border)]">
                        ⌘K
                      </kbd>{' '}
                      (یا Ctrl+K) به همه بخشها سریع بروید.
                    </p>
                  </div>

                  <div className="card p-5 slide-up" style={{ animationDelay: '0.1s' }}>
                    <div className="w-11 h-11 rounded-xl bg-[var(--bg-elevated)] flex items-center justify-center mb-3">
                      <Icon name="models" size={22} className="text-[var(--accent)]" />
                    </div>
                    <div className="font-semibold mb-1">تعویض مدل</div>
                    <p className="text-xs text-[var(--text-muted)] leading-relaxed">
                      مدل فعال را از نوار بالای صفحه چت با یک کلیک عوض کنید.
                    </p>
                  </div>

                  <div className="card p-5 slide-up" style={{ animationDelay: '0.15s' }}>
                    <div className="w-11 h-11 rounded-xl bg-[var(--bg-elevated)] flex items-center justify-center mb-3">
                      <Icon name="wallet" size={22} className="text-[var(--accent)]" />
                    </div>
                    <div className="font-semibold mb-1">موجودی حساب</div>
                    <p className="text-xs text-[var(--text-muted)] leading-relaxed">
                      هزینه هر چت و موجودی خود را از بخش «کیف پول» دنبال کنید.
                    </p>
                  </div>
                </div>

                <div className="flex items-center justify-between mt-8 gap-3">
                  <button className="btn btn-ghost" onClick={() => setStep(3)}>
                    <Icon name="arrowRight" size={16} />
                    قبلی
                  </button>
                  <button className="btn btn-primary btn-lg" onClick={finish} disabled={redirecting}>
                    {redirecting ? 'در حال انتقال...' : 'شروع چت'}
                    <Icon name="send" size={18} />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
