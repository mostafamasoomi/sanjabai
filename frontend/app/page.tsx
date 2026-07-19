'use client'

import Link from 'next/link'
import { useEffect, useState, useRef } from 'react'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { getClaim, modelCountLabel } from '@/lib/claims'
import { type ModelCatalogItem, type CatalogResponse } from '@/types/catalog'

/* ═══════════════════════════════════════════════════════════════════════════
   Multiai Landing — v3 Redesign
   Asymmetric layout, scroll-triggered reveals, spring animations, dark aesthetic.
   Design principles: Emil Kowalski (design-engineering) + Linear-inspired.
   ═══════════════════════════════════════════════════════════════════════════ */

const FEATURES = [
  { icon: 'models' as const, title: 'همه مدلها، یک پنل', desc: getClaim('workspace_promise'), color: '#6366f1' },
  { icon: 'dashboard' as const, title: 'مدیریت هوشمند مصرف', desc: 'داشبورد لحظهای، سقف مصرف و هشدار — کنترل کامل روی بودجه', color: '#8b5cf6' },
  { icon: 'pricing' as const, title: 'قیمتگذاری شفاف', desc: getClaim('currency_transparency'), color: '#06b6d4' },
  { icon: 'security' as const, title: 'امن و مستقل', desc: 'سرورهای اختصاصی، بدون وابستگی به تحریم — دادههای شما محفوظ است', color: '#10b981' },
  { icon: 'code' as const, title: 'API آماده', desc: 'OpenAI-compatible — در ۲ دقیقه کلید API بسازید و متصل شوید', color: '#f59e0b' },
  { icon: 'chat' as const, title: 'فارسی واقعی', desc: 'رابط کاملاً فارسی، پشتیبانی از زبان فارسی در تمام مدلها', color: '#ec4899' },
]

const STEPS = [
  { icon: 'profile' as const, title: 'ثبتنام', desc: 'در ۳۰ ثانیه حساب بسازید' },
  { icon: 'wallet' as const, title: 'شارژ', desc: 'کیف پول ریالی' },
  { icon: 'chat' as const, title: 'چت', desc: 'با بهترین مدلها' },
  { icon: 'dashboard' as const, title: 'مدیریت', desc: 'پیگیری مصرف و هزینه' },
]

const FAQ = [
  { q: 'Multiai چه فرقی با ChatGPT دارد؟', a: 'Multiai یک پلتفرم یکپارچه است — به بهترین مدلهای هوش مصنوعی دنیا از یک پنل دسترسی دارید، با قیمت ریالی و بدون نیاز به VPN.' },
  { q: 'آیا نیاز به VPN دارم؟', a: 'خیر. تمام ارتباطات از طریق زیرساخت اختصاصی و داخلی مسیریابی میشود.' },
  { q: 'هزینه استفاده چقدر است؟', a: 'تعرفهها بر اساس مدل متفاوت است. هزینه دقیق را قبل از ارسال هر درخواست میبینید.' },
  { q: 'اطلاعات من امن است؟', a: 'بله. تمام ارتباطات رمزنگاری شده و دادهها روی سرورهای اختصاصی ذخیره میشوند.' },
  { q: 'چطور API key بسازم؟', a: 'بعد از ثبتنام، از بخش «کلید API» یک کلید جدید بسازید. endpoint ما با OpenAI-compatible است.' },
]

/* ═══════════════════════════════════════════════════════════════════════════
   Scroll Reveal Hook
   ═══════════════════════════════════════════════════════════════════════════ */

function useReveal() {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setVisible(true) },
      { threshold: 0.15, rootMargin: '0px 0px -40px 0px' }
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  return { ref, visible }
}

/* ═══════════════════════════════════════════════════════════════════════════
   Hero — Asymmetric: 3D orbs left, content right
   ═══════════════════════════════════════════════════════════════════════════ */

function Hero({ isLoggedIn, modelCount }: { isLoggedIn: boolean; modelCount: string }) {
  return (
    <section className="relative min-h-[90vh] flex items-center overflow-hidden hero-grid-bg">
      {/* Background orbs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
        <div className="hero-orb absolute -top-32 -right-32 w-[500px] h-[500px] rounded-full opacity-20"
          style={{ background: 'radial-gradient(circle, rgba(99,102,241,0.4), transparent 70%)' }} />
        <div className="hero-orb-2 absolute top-1/2 -left-32 w-[400px] h-[400px] rounded-full opacity-15"
          style={{ background: 'radial-gradient(circle, rgba(168,85,247,0.4), transparent 70%)' }} />
        <div className="hero-orb-3 absolute -bottom-32 right-1/4 w-[350px] h-[350px] rounded-full opacity-15"
          style={{ background: 'radial-gradient(circle, rgba(6,182,212,0.3), transparent 70%)' }} />
      </div>

      <div className="relative z-10 w-full max-w-6xl mx-auto px-6 md:px-12 py-20 md:py-32">
        <div className="flex flex-col items-center text-center">
          {/* Status badge */}
          <div className="inline-flex items-center gap-2 px-5 py-2 rounded-full border border-[var(--border)] bg-[var(--bg-surface)]/80 backdrop-blur-sm mb-10">
            <span className="relative flex h-2.5 w-2.5">
              <span className="pulse-ring absolute inline-flex h-full w-full rounded-full bg-[var(--positive)]" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[var(--positive)]" />
            </span>
            <span className="text-sm text-[var(--text-secondary)]">{modelCount}</span>
          </div>

          {/* Headline */}
          <h1 className="text-4xl sm:text-5xl md:text-7xl font-extrabold leading-[1.05] tracking-tight max-w-3xl">
            <span className="text-gradient-animated">هوش مصنوعی</span>
            <br />
            <span className="text-[var(--text-primary)]">برای همه، به زبان فارسی</span>
          </h1>

          {/* Description */}
          <p className="text-base sm:text-lg text-[var(--text-secondary)] mt-8 max-w-xl leading-relaxed">
            {getClaim('workspace_promise')}
          </p>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center mt-10">
            <Link
              href={isLoggedIn ? '/chat' : '/signup'}
              className="btn-spring btn btn-primary btn-lg text-base px-12 py-4 rounded-xl font-semibold"
              style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', boxShadow: '0 4px 32px rgba(99,102,241,0.4), 0 0 64px rgba(99,102,241,0.15)' }}
            >
              {isLoggedIn ? 'شروع چت' : 'شروع رایگان'}
              <Icon name="arrowRight" size={18} />
            </Link>
            <Link
              href="/models"
              className="btn-spring btn btn-secondary btn-lg text-base px-12 py-4 rounded-xl font-medium"
              style={{ borderColor: 'rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.03)' }}
            >
              مشاهده مدلها
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Stats Bar — with reveal animation
   ═══════════════════════════════════════════════════════════════════════════ */

function StatsBar({ modelCount }: { modelCount: string }) {
  const { ref, visible } = useReveal()
  const stats = [
    { value: modelCount, label: 'در دسترس هماکنون' },
    { value: 'شفاف', label: 'قیمتگذاری ریالی' },
    { value: 'بدون VPN', label: 'دسترسی مستقیم' },
    { value: '< ۲ دقیقه', label: 'شروع استفاده' },
  ]

  return (
    <div ref={ref} className={`reveal-section ${visible ? 'visible' : ''}`}>
      <div className="max-w-4xl mx-auto px-6 py-12">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {stats.map((s, i) => (
            <div key={i} className="text-center p-6 rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)]/50">
              <div className="text-2xl md:text-3xl font-bold text-[var(--text-primary)] mb-1">{s.value}</div>
              <div className="text-xs text-[var(--text-muted)]">{s.label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Features — alternating layout with stagger reveal
   ═══════════════════════════════════════════════════════════════════════════ */

function Features() {
  const { ref, visible } = useReveal()

  return (
    <section ref={ref} className="py-20 md:py-28">
      <div className="max-w-6xl mx-auto px-6 md:px-12">
        <div className={`reveal-section ${visible ? 'visible' : ''}`}>
          <h2 className="text-3xl md:text-4xl font-bold text-center text-[var(--text-primary)] mb-4">
            چرا Multiai؟
          </h2>
          <p className="text-[var(--text-secondary)] text-center mb-16 max-w-lg mx-auto">
            پلتفرمی که تجربه کار با هوش مصنوعی را برای کاربران ایرانی متحول میکند
          </p>
        </div>

        <div className={`reveal-stagger ${visible ? 'visible' : ''}`}>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {FEATURES.map((f) => (
              <div key={f.title} className="feature-card-hover card p-6 rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)]/60">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center mb-5" style={{ background: `${f.color}15` }}>
                  <Icon name={f.icon} size={24} style={{ color: f.color }} />
                </div>
                <h3 className="font-bold text-lg text-[var(--text-primary)] mb-2">{f.title}</h3>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Steps — Horizontal timeline with pulse
   ═══════════════════════════════════════════════════════════════════════════ */

function Steps() {
  const { ref, visible } = useReveal()

  return (
    <section ref={ref} className="py-20 md:py-28 bg-[var(--bg-surface)]/30">
      <div className="max-w-4xl mx-auto px-6 md:px-12">
        <div className={`reveal-section ${visible ? 'visible' : ''}`}>
          <h2 className="text-3xl md:text-4xl font-bold text-center text-[var(--text-primary)] mb-4">
            چطور شروع کنم؟
          </h2>
          <p className="text-[var(--text-secondary)] text-center mb-16">
            ۴ قدم ساده تا دسترسی به هوش مصنوعی
          </p>
        </div>

        <div className={`reveal-stagger ${visible ? 'visible' : ''}`}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {STEPS.map((s, i) => (
              <div key={s.title} className="text-center p-6">
                <div className="relative inline-flex mb-4">
                  <div className="w-14 h-14 rounded-2xl bg-[var(--accent-dim)] flex items-center justify-center relative z-10">
                    <span className="text-lg font-bold text-[var(--accent)]">{i + 1}</span>
                  </div>
                  {i < STEPS.length - 1 && (
                    <div className="hidden md:block absolute top-1/2 left-full w-8 h-0.5 bg-[var(--border)] -translate-y-1/2" />
                  )}
                </div>
                <h3 className="font-bold text-[var(--text-primary)] mb-1">{s.title}</h3>
                <p className="text-xs text-[var(--text-muted)]">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   CTA Banner — with glow
   ═══════════════════════════════════════════════════════════════════════════ */

function CTABanner({ isLoggedIn }: { isLoggedIn: boolean }) {
  const { ref, visible } = useReveal()

  return (
    <section ref={ref} className={`py-20 md:py-28 reveal-section ${visible ? 'visible' : ''}`}>
      <div className="max-w-3xl mx-auto px-6">
        <div className="relative overflow-hidden rounded-3xl p-10 md:p-16 text-center"
          style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.08), rgba(168,85,247,0.06))', border: '1px solid rgba(99,102,241,0.15)' }}>
          <div className="absolute inset-0 pointer-events-none" aria-hidden="true"
            style={{ background: 'radial-gradient(circle at 50% 0%, rgba(99,102,241,0.15), transparent 60%)' }} />
          <div className="relative z-10">
            <h2 className="text-2xl md:text-4xl font-bold text-[var(--text-primary)] mb-4">آماده شروع هستید؟</h2>
            <p className="text-[var(--text-secondary)] mb-8 max-w-md mx-auto">
              همین حالا ثبتنام کنید و به پیشرفتهترین مدلهای هوش مصنوعی دسترسی پیدا کنید.
            </p>
            <Link
              href={isLoggedIn ? '/chat' : '/signup'}
              className="btn-spring btn btn-primary btn-lg text-base px-12 py-4 rounded-xl font-semibold inline-flex items-center gap-2"
              style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', boxShadow: '0 4px 32px rgba(99,102,241,0.4)' }}
            >
              {isLoggedIn ? 'رفتن به چت' : 'شروع رایگان'}
              <Icon name="arrowRight" size={18} />
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   FAQ — Spring accordion
   ═══════════════════════════════════════════════════════════════════════════ */

function FAQSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(null)
  const { ref, visible } = useReveal()

  return (
    <section ref={ref} className="py-20 md:py-28">
      <div className="max-w-2xl mx-auto px-6">
        <div className={`reveal-section ${visible ? 'visible' : ''}`}>
          <h2 className="text-3xl md:text-4xl font-bold text-center text-[var(--text-primary)] mb-12">
            سوالات متداول
          </h2>
        </div>

        <div className={`reveal-stagger ${visible ? 'visible' : ''}`}>
          <div className="space-y-3">
            {FAQ.map((item, i) => {
              const isOpen = openIndex === i
              return (
                <div key={item.q} className="card border border-[var(--border)] rounded-2xl overflow-hidden">
                  <button
                    type="button"
                    className="w-full px-6 py-5 text-right flex items-center justify-between gap-4 hover:bg-[var(--bg-hover)] transition-colors"
                    onClick={() => setOpenIndex(isOpen ? null : i)}
                    aria-expanded={isOpen}
                  >
                    <span className="font-medium text-[var(--text-primary)]">{item.q}</span>
                    <Icon name="arrowRight" size={16}
                      className={`text-[var(--text-muted)] shrink-0 transition-transform duration-300 ${isOpen ? 'rotate-90' : ''}`} />
                  </button>
                  <div className={`faq-answer-spring ${isOpen ? 'open' : ''}`}>
                    <div>
                      <p className="px-6 pb-5 text-sm text-[var(--text-secondary)] leading-relaxed">{item.a}</p>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Page
   ═══════════════════════════════════════════════════════════════════════════ */

export default function LandingPage() {
  const { user } = useAuth()
  const isLoggedIn = !!user

  const [models, setModels] = useState<ModelCatalogItem[]>([])
  const [modelsLoaded, setModelsLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch('/api/catalog/models')
      .then((res) => res.json())
      .then((data: CatalogResponse) => {
        if (cancelled) return
        setModels(data?.data ?? [])
      })
      .catch((err) => { console.error('Failed to fetch catalog:', err) })
      .finally(() => {
        if (!cancelled) setModelsLoaded(true)
      })
    return () => { cancelled = true }
  }, [])

  const modelCount = modelsLoaded ? modelCountLabel(models) : 'در حال بارگذاری...'

  return (
    <div className="landing-v3">
      <Hero isLoggedIn={isLoggedIn} modelCount={modelCount} />
      <StatsBar modelCount={modelCount} />
      <Features />
      <Steps />
      <CTABanner isLoggedIn={isLoggedIn} />
      <FAQSection />
      <footer className="text-center py-12 text-xs text-[var(--text-muted)] border-t border-[var(--border)]">
        <p>Multiai — دسترسی به هوش مصنوعی برای همه</p>
      </footer>
    </div>
  )
}