'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { getClaim, modelCountLabel } from '@/lib/claims'
import { type ModelCatalogItem, type CatalogResponse } from '@/types/catalog'

/* ═══════════════════════════════════════════════════════════════════════════
   Multiai Landing — Aurora v2 Enhanced
   Conversion-first, trust-building, fast.
   Claims are sourced from the claim registry, not hardcoded literals.
   ═══════════════════════════════════════════════════════════════════════════ */

const FEATURES = [
  { icon: 'models' as const, title: 'همه مدلها، یک پنل', desc: getClaim('workspace_promise') },
  { icon: 'dashboard' as const, title: 'مدیریت هوشمند مصرف', desc: 'داشبورد لحظهای، سقف مصرف و هشدار — کنترل کامل روی بودجه' },
  { icon: 'pricing' as const, title: 'قیمت‌گذاری شفاف', desc: getClaim('currency_transparency') },
  { icon: 'security' as const, title: 'امن و مستقل', desc: 'سرورهای اختصاصی، بدون وابستگی به تحریم — دادههای شما محفوظ است' },
  { icon: 'code' as const, title: 'API آماده', desc: 'OpenAI-compatible — در ۲ دقیقه کلید API بسازید و متصل شوید' },
  { icon: 'chat' as const, title: 'فارسی واقعی', desc: 'رابط کاملاً فارسی، پشتیبانی از زبان فارسی در تمام مدلها' },
]

const STEPS = [
  { icon: 'profile' as const, title: 'ثبت‌نام', desc: 'در ۳۰ ثانیه حساب بسازید' },
  { icon: 'wallet' as const, title: 'شارژ', desc: 'کیف پول ریالی خود را شارژ کنید' },
  { icon: 'chat' as const, title: 'چت', desc: 'با بهترین مدلها گفتگو کنید' },
  { icon: 'dashboard' as const, title: 'مدیریت', desc: 'مصرف و هزینه را پیگیری کنید' },
]

const STATS = [
  { value: '۸ مدل', label: 'در دسترس هم‌اکنون' },
  { value: 'شفاف', label: 'قیمت‌گذاری ریالی' },
  { value: 'بدون VPN', label: 'دسترسی مستقیم' },
  { value: '< ۲ دقیقه', label: 'شروع استفاده' },
]

const FAQ = [
  { q: 'Multiai چه فرقی با ChatGPT دارد؟', a: 'Multiai یک پلتفرم یکپارچه است — به بهترین مدلهای هوش مصنوعی دنیا از یک پنل دسترسی دارید، با قیمت ریالی و بدون نیاز به VPN.' },
  { q: 'آیا نیاز به VPN دارم؟', a: 'خیر. تمام ارتباطات از طریق زیرساخت اختصاصی و داخلی مسیریابی می‌شود.' },
  { q: 'هزینه استفاده چقدر است؟', a: 'تعرفهها بر اساس مدل متفاوت است. هزینه دقیق را قبل از ارسال هر درخواست میبینید.' },
  { q: 'اطلاعات من امن است؟', a: 'بله. تمام ارتباطات رمزنگاری شده و دادهها روی سرورهای اختصاصی ذخیره میشوند. ما به حریم خصوصی شما احترام میگذاریم.' },
  { q: 'چطور API key بسازم؟', a: 'بعد از ثبت‌نام، از بخش «کلید API» یک کلید جدید بسازید. endpoint ما با OpenAI-compatible است و کد نمونه برای cURL، Python و JavaScript آماده داریم.' },
]

/* ═══════════════════════════════════════════════════════════════════════════
   Hero
   ═══════════════════════════════════════════════════════════════════════════ */

function Hero({ isLoggedIn, modelCount }: { isLoggedIn: boolean; modelCount: string }) {
  return (
    <section className="aurora-hero-section relative text-center py-16 md:py-24 overflow-hidden">
      {/* Gradient mesh background */}
      <div className="aurora-hero-mesh" aria-hidden="true">
        <div className="aurora-mesh-orb aurora-mesh-orb-1" />
        <div className="aurora-mesh-orb aurora-mesh-orb-2" />
        <div className="aurora-mesh-orb aurora-mesh-orb-3" />
      </div>

      <div className="aurora-fade-in-up relative">
        <div className="aurora-hero-badge inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--border)] bg-[var(--bg-surface)]/80 backdrop-blur-sm mb-8 text-sm">
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--positive)] opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[var(--positive)]" />
          </span>
          <span className="text-[var(--text-secondary)]">{modelCount}</span>
        </div>

        <h1 className="aurora-hero-title text-4xl sm:text-5xl md:text-6xl font-extrabold leading-tight tracking-tight">
          <span className="text-gradient">هوش مصنوعی</span>
          <br />
          <span>برای همه، به زبان فارسی</span>
        </h1>

        <p className="aurora-hero-desc text-base sm:text-lg text-[var(--text-secondary)] mt-6 max-w-xl mx-auto leading-relaxed">
          {getClaim('workspace_promise')}
        </p>

        <div className="flex flex-col sm:flex-row gap-3 justify-center mt-8">
          <Link href={isLoggedIn ? '/chat' : '/signup'} className="aurora-cta-glow btn btn-primary btn-lg text-base px-10 py-3.5" style={{boxShadow: '0 4px 24px var(--accent-glow), 0 0 48px var(--accent-dim)'}}>
            {isLoggedIn ? 'شروع چت' : 'شروع رایگان'}
            <Icon name="arrowRight" size={18} />
          </Link>
          <Link href="/models" className="btn btn-secondary btn-lg text-base px-10 py-3.5" style={{borderColor: 'rgba(255,255,255,0.1)'}}>
            مشاهده مدلها
          </Link>
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Dollar Ticker — Live USD→IRT from tgju.org
   ═══════════════════════════════════════════════════════════════════════════ */

function DollarTicker() {
  const [rate, setRate] = useState<{ usd_to_irt: number; source: string } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    fetch('/api/exchange-rate')
      .then((r) => r.json())
      .then((d) => { if (!cancelled) setRate(d) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const irt = rate?.usd_to_irt
  const formatted = irt ? new Intl.NumberFormat('fa-IR').format(irt) : '—'

  return (
    <div className="aurora-fade-in-up flex justify-center mb-4">
      <div className="inline-flex items-center gap-3 px-5 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-surface)]/70 backdrop-blur-sm text-sm">
        <span className="flex items-center gap-1.5">
          <span className="text-lg">💵</span>
          <span className="text-[var(--text-muted)]">دلار آزاد</span>
        </span>
        <span className="w-px h-5 bg-[var(--border)]" />
        {loading ? (
          <span className="text-[var(--text-muted)]">...</span>
        ) : (
          <span className="font-bold text-[var(--text-primary)] tabular-nums tracking-wide">
            {formatted} <span className="text-xs text-[var(--text-muted)]">تومان</span>
          </span>
        )}
        {rate?.source && rate.source !== 'fallback' && (
          <span className="text-[10px] text-[var(--text-muted)] bg-[var(--bg-hover)] px-1.5 py-0.5 rounded">
            {rate.source === 'tgju.org' ? 'لحظه‌ای' : rate.source}
          </span>
        )}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Stats Bar
   ═══════════════════════════════════════════════════════════════════════════ */

function StatsBar() {
  return (
    <div className="aurora-stats-bar aurora-fade-in-up">
      {STATS.map((s, i) => (
        <div key={i} className="aurora-stat-item">
          <span className="aurora-stat-value">{s.value}</span>
          <span className="aurora-stat-label">{s.label}</span>
        </div>
      ))}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Features
   ═══════════════════════════════════════════════════════════════════════════ */

function Features() {
  return (
    <section className="py-16">
      <div className="text-center mb-12">
        <h2 className="aurora-section-title text-2xl md:text-3xl font-bold">چرا Multiai؟</h2>
        <p className="text-[var(--text-secondary)] mt-3 max-w-md mx-auto">
          پلتفرمی که تجربه کار با هوش مصنوعی را برای کاربران ایرانی متحول می‌کند
        </p>
      </div>
      <div className="aurora-features-grid grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {FEATURES.map((f, i) => (
          <div key={f.title} className="aurora-feature-card card card-interactive group" style={{ animationDelay: `${i * 80}ms` }}>
            <div className="aurora-feature-icon w-10 h-10 rounded-lg flex items-center justify-center mb-4">
              <Icon name={f.icon} size={22} className="text-[var(--accent)]" />
            </div>
            <h3 className="font-bold text-base mb-1.5">{f.title}</h3>
            <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{f.desc}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   How it works — Vertical Timeline
   ═══════════════════════════════════════════════════════════════════════════ */

function Steps() {
  return (
    <section className="py-16">
      <div className="text-center mb-12">
        <h2 className="aurora-section-title text-2xl font-bold">چطور شروع کنم؟</h2>
        <p className="text-[var(--text-secondary)] mt-3">۴ قدم ساده تا دسترسی به هوش مصنوعی</p>
      </div>
      <div className="aurora-timeline max-w-lg mx-auto">
        {STEPS.map((s, i) => (
          <div key={s.title} className="aurora-timeline-step" style={{ animationDelay: `${i * 120}ms` }}>
            <div className="aurora-timeline-connector">
              <div className="aurora-timeline-dot">
                <span className="aurora-timeline-number">{i + 1}</span>
              </div>
              {i < STEPS.length - 1 && <div className="aurora-timeline-line" />}
            </div>
            <div className="aurora-timeline-content card card-interactive">
              <div className="w-10 h-10 rounded-lg bg-[var(--accent-dim)] flex items-center justify-center mb-3">
                <Icon name={s.icon} size={20} className="text-[var(--accent)]" />
              </div>
              <h3 className="font-bold mb-1">{s.title}</h3>
              <p className="text-sm text-[var(--text-secondary)]">{s.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   CTA Banner with accent glow
   ═══════════════════════════════════════════════════════════════════════════ */

function CTABanner({ isLoggedIn }: { isLoggedIn: boolean }) {
  return (
    <section className="py-16">
      <div className="aurora-cta-card card text-center relative overflow-hidden">
        <div className="aurora-cta-glow-bg" aria-hidden="true" />
        <div className="relative z-10">
          <h2 className="text-2xl md:text-3xl font-bold mb-3">آماده شروع هستید؟</h2>
          <p className="text-[var(--text-secondary)] mb-6 max-w-md mx-auto">
            همین حالا ثبت‌نام کنید و به پیشرفتهترین مدلهای هوش مصنوعی دسترسی پیدا کنید.
          </p>
          <Link href={isLoggedIn ? '/chat' : '/signup'} className="aurora-cta-glow btn btn-primary btn-lg text-base px-8">
            {isLoggedIn ? 'رفتن به چت' : 'شروع رایگان'}
            <Icon name="arrowRight" size={18} />
          </Link>
        </div>
      </div>
    </section>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   FAQ — Animated Accordion
   ═══════════════════════════════════════════════════════════════════════════ */

function FAQSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(null)

  return (
    <section className="py-16">
      <div className="text-center mb-12">
        <h2 className="aurora-section-title text-2xl font-bold">سوالات متداول</h2>
      </div>
      <div className="max-w-2xl mx-auto space-y-3">
        {FAQ.map((item, i) => {
          const isOpen = openIndex === i
          return (
            <div key={item.q} className={`aurora-faq-item card cursor-pointer ${isOpen ? 'aurora-faq-open' : ''}`}>
              <button
                type="button"
                className="w-full font-medium text-sm flex items-center justify-between text-right"
                onClick={() => setOpenIndex(isOpen ? null : i)}
                aria-expanded={isOpen}
              >
                <span>{item.q}</span>
                <Icon name="arrowRight" size={16} className={`aurora-faq-chevron text-[var(--text-muted)] ${isOpen ? 'aurora-faq-chevron-open' : ''}`} />
              </button>
              <div className={`aurora-faq-answer ${isOpen ? 'aurora-faq-answer-open' : ''}`}>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{item.a}</p>
              </div>
            </div>
          )
        })}
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
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setModelsLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const modelCount = modelsLoaded ? modelCountLabel(models) : 'در حال بارگذاری...'

  return (
    <>
      <Hero isLoggedIn={isLoggedIn} modelCount={modelCount} />
      <DollarTicker />
      <StatsBar />
      <Features />
      <Steps />
      <CTABanner isLoggedIn={isLoggedIn} />
      <FAQSection />
      <footer className="aurora-footer text-center py-10 text-xs text-[var(--text-muted)] border-t border-[var(--border)]">
        <p>Multiai — دسترسی به هوش مصنوعی برای همه</p>
      </footer>
    </>
  )
}
