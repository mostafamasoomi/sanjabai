'use client'

import Link from 'next/link'
import { useEffect, useState, useRef } from 'react'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { modelCountLabel } from '@/lib/claims'
import { type ModelCatalogItem, type CatalogResponse } from '@/types/catalog'
import VortexParticles from '@/components/VortexParticles'

/* ═══════════════════════════════════════════════════════════════════════════
   Multiai Landing v6 — Full motion.page DNA
   Canvas particles, ultra-thin typography, glass badges, conic dots,
   staggered reveals. Built on real platform capabilities.
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Reveal hook ──────────────────────────────────────────────────────── */

function useReveal(threshold = 0.15) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const el = ref.current; if (!el) return
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) setVisible(true) }, { threshold })
    obs.observe(el); return () => obs.disconnect()
  }, [threshold])
  return { ref, visible }
}

/* ── Platform marquee ─────────────────────────────────────────────────── */

const PLATFORMS = [
  'DeepSeek V4', 'Mistral Large', 'Tencent HY-3', 'MiMo Pro',
  'GPT-4o', 'Claude 3.5', 'Gemini', 'Llama 3', 'Qwen',
  'Smart Mode', 'OpenAI API', 'RAG',
]

function PlatformMarquee() {
  return (
    <div className="platform-marquee">
      <div className="platform-marquee-inner">
        {[...PLATFORMS, ...PLATFORMS].map((p, i) => (
          <span key={i} className="platform-chip">
            <span className="conic-dot" />
            {p}
          </span>
        ))}
      </div>
    </div>
  )
}

/* ── Staggered dot grid ───────────────────────────────────────────────── */

function DotGrid() {
  return (
    <div className="dot-grid" aria-hidden="true">
      {Array.from({ length: 30 }).map((_, i) => {
        const x = 5 + Math.random() * 90
        const y = 5 + Math.random() * 90
        const delay = Math.random() * 3
        return (
          <span key={i} className="dot" style={{ left: `${x}%`, top: `${y}%`, animationDelay: `${delay}s` }} />
        )
      })}
    </div>
  )
}

/* ── Hero ─────────────────────────────────────────────────────────────── */

function Hero({ isLoggedIn, modelCount }: { isLoggedIn: boolean; modelCount: string }) {
  return (
    <section className="hero-section">
      <VortexParticles />
      <DotGrid />

      <div className="relative z-10 w-full max-w-4xl mx-auto px-6 py-20 text-center">
        {/* Glass badge */}
        <div className="inline-flex mb-10">
          <span className="glass-badge">
            <span className="live-dot" />
            {modelCount}
            <span className="conic-dot" />
          </span>
        </div>

        {/* Headline — ultra-thin, motion.page style */}
        <h1 className="hero-headline mb-6">
          پلتفرم
          {' '}
          <span className="accent">کامل</span>
          {' '}
          هوش مصنوعی
          <br />
          <span className="accent">فارسی</span>
          .
        </h1>

        <p className="text-base sm:text-lg max-w-xl mx-auto leading-relaxed mb-10" style={{ color: 'var(--text-muted)' }}>
          دسترسی به پیشرفته‌ترین مدل‌های هوش مصنوعی دنیا.
          پرداخت ریالی، بدون VPN، API سازگار با OpenAI.
        </p>

        {/* CTAs — white primary (motion.page style) */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link href={isLoggedIn ? '/chat' : '/signup'} className="cta-primary">
            {isLoggedIn ? 'شروع چت' : 'شروع رایگان'}
            <Icon name="arrowRight" size={16} />
          </Link>
          <Link href="/models" className="cta-secondary">
            مشاهده مدل‌ها
          </Link>
        </div>
      </div>
    </section>
  )
}

/* ── Stats ────────────────────────────────────────────────────────────── */

function Stats({ modelCount }: { modelCount: string }) {
  const { ref, visible } = useReveal()
  return (
    <div ref={ref} className="max-w-4xl mx-auto px-6 -mt-16 relative z-20">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { value: modelCount, label: 'مدل در دسترس' },
          { value: 'پرداخت ریالی', label: 'تومان، بدون ارز' },
          { value: 'بدون VPN', label: 'دسترسی مستقیم' },
          { value: 'API آماده', label: 'OpenAI-compatible' },
        ].map((s, i) => (
          <div key={i} className="capability-card text-center reveal"
            style={{ transitionDelay: `${i * 80}ms`, opacity: visible ? 1 : undefined, transform: visible ? 'none' : undefined }}>
            <div className="stat-number">{s.value}</div>
            <div className="stat-label">{s.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── Capabilities ─────────────────────────────────────────────────────── */

const CAPABILITIES = [
  { icon: 'chat', title: 'چت هوشمند', desc: 'مکالمه با برترین مدل‌ها — streaming实时، Markdown، syntax highlighting و web search.' },
  { icon: 'code', title: 'API سازگار با OpenAI', desc: 'در ۲ دقیقه کلید API بسازید. با تمام کتابخونه‌های استاندارد کار میکنه.' },
  { icon: 'models', title: 'Smart Mode', desc: 'هوش مصنوعی خودش بهترین مدل رو انتخاب میکنه — همیشه cheapest capable model.' },
  { icon: 'dashboard', title: 'داشبورد و مدیریت', desc: 'پیگیری لحظه‌ای مصرف، تاریخچه تراکنش‌ها، شارژ ریالی از طریق زرین‌پال.' },
  { icon: 'search', title: 'جستجوی وب', desc: 'DuckDuckGo + Wikipedia — نتایج زنده بدون API key.' },
  { icon: 'security', title: 'امن و مستقل', desc: 'سرورهای اختصاصی، رمزنگاری کامل، بدون تحریم. مکالمات شما private.' },
  { icon: 'prompts', title: 'حافظه و اسکیلز', desc: 'مدل مکالمات مهم رو به خاطر میسپره. اسکیلز marketplace برای تخصص‌های مختلف.' },
  { icon: 'tasks', title: 'تسک‌های زمان‌بندی', desc: 'پرامپت‌های recurring تنظیم کنید. تحویل از طریق dashboard یا Telegram.' },
  { icon: 'documents', title: 'RAG و آپلود فایل', desc: 'آپلود PDF, TXT, CSV, JSON — مدل محتواش رو میخونه و بهش استناد میکنه.' },
]

function Capabilities() {
  const { ref, visible } = useReveal()
  return (
    <section ref={ref} className="py-24 md:py-32">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-16">
          <p className="section-eyebrow">قابلیت‌ها</p>
          <h2 className="section-heading mb-4">
            هر چیزی که برای کار با
            {' '}
            <span style={{ color: 'var(--accent)' }}>هوش مصنوعی</span>
            {' '}
            نیاز دارید
          </h2>
          <p style={{ color: 'var(--text-muted)', maxWidth: '36rem', margin: '0 auto' }}>
            از چت ساده تا API سازمانی — همه در یک پلتفرم، با قیمت ریالی و بدون تحریم.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {CAPABILITIES.map((c, i) => (
            <div key={c.title} className="capability-card reveal"
              style={{ transitionDelay: `${i * 60}ms`, opacity: visible ? 1 : undefined, transform: visible ? 'none' : undefined }}>
              <div className="capability-icon">
                <Icon name={c.icon as any} size={18} />
              </div>
              <h3 className="font-medium text-[var(--text-primary)] mb-1.5">{c.title}</h3>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>{c.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── How it works ─────────────────────────────────────────────────────── */

const STEPS = [
  { step: '۱', title: 'ثبت‌نام', desc: '۳۰ ثانیه، فقط ایمیل' },
  { step: '۲', title: 'شارژ کیف پول', desc: 'پرداخت ریالی، زرین‌پال' },
  { step: '۳', title: 'چت یا API', desc: 'انتخاب مدل، شروع' },
  { step: '۴', title: 'پیگیری مصرف', desc: 'داشبورد لحظه‌ای' },
]

function HowItWorks() {
  const { ref, visible } = useReveal()
  return (
    <section ref={ref} className="py-24 md:py-32" style={{ background: 'rgba(129,140,248,0.02)' }}>
      <div className="max-w-3xl mx-auto px-6">
        <div className="text-center mb-16">
          <p className="section-eyebrow">شروع کنید</p>
          <h2 className="section-heading">چطور کار میکنه؟</h2>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {STEPS.map((s, i) => (
            <div key={s.title} className="reveal text-center"
              style={{ transitionDelay: `${i * 100}ms`, opacity: visible ? 1 : undefined, transform: visible ? 'none' : undefined }}>
              <div className="w-12 h-12 rounded-xl mx-auto mb-3 flex items-center justify-center text-lg"
                style={{ background: 'var(--accent-dim)', color: 'var(--accent)', fontWeight: 300 }}>
                {s.step}
              </div>
              <h3 className="font-medium text-[var(--text-primary)] mb-1">{s.title}</h3>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{s.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── Pricing ──────────────────────────────────────────────────────────── */

function Pricing({ isLoggedIn, modelCount }: { isLoggedIn: boolean; modelCount: string }) {
  const { ref, visible } = useReveal()
  return (
    <section ref={ref} className="py-24 md:py-32">
      <div className="max-w-5xl mx-auto px-6">
        <div className="text-center mb-16">
          <p className="section-eyebrow">تعرفه‌ها</p>
          <h2 className="section-heading mb-4">
            قیمت‌گذاری
            {' '}
            <span style={{ color: 'var(--accent)' }}>شفاف</span>
            {' '}
            و ساده
          </h2>
          <p style={{ color: 'var(--text-muted)', maxWidth: '36rem', margin: '0 auto' }}>
            {modelCount} — فقط به اندازه مصرف واقعی پرداخت کنید.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            { name: 'رایگان', price: '۰ تومان', desc: 'شروع بدون هزینه', features: ['مدل Tencent HY-3', 'Smart Mode رایگان', 'API تا ۱۰۰ درخواست', 'چت با web search'], cta: 'شروع رایگان', href: '/signup' },
            { name: 'اعتباری', price: 'پرداخت به ازای مصرف', desc: 'محبوب‌ترین', features: ['همه مدل‌ها', 'DeepSeek V4 Pro', 'Mistral Large', 'MiMo Pro', 'API نامحدود', 'RAG و آپلود فایل', 'اسکیلز و حافظه'], cta: 'مشاهده مدل‌ها', href: '/models', featured: true },
            { name: 'اشتراکی', price: 'طرح‌های ماهانه', desc: 'حرفه‌ای', features: ['سقف مصرف بالاتر', 'اولویت در صف', 'مدل‌های premium', 'تسک‌های زمان‌بندی', 'پشتیبانی اختصاصی'], cta: 'مشاهده طرح‌ها', href: '/pricing' },
          ].map((p, i) => (
            <div key={p.name} className={`pricing-card${p.featured ? ' featured' : ''} reveal`}
              style={{ transitionDelay: `${i * 100}ms`, opacity: visible ? 1 : undefined, transform: visible ? 'none' : undefined }}>
              <h3 className="text-lg font-medium text-[var(--text-primary)] mb-1">{p.name}</h3>
              <p className="text-2xl mb-1" style={{ color: 'var(--accent)', fontWeight: 300 }}>{p.price}</p>
              <p className="text-sm mb-6" style={{ color: 'var(--text-muted)' }}>{p.desc}</p>
              <ul className="space-y-2.5 mb-8">
                {p.features.map(f => (
                  <li key={f} className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-muted)' }}>
                    <Icon name="check" size={12} style={{ color: 'var(--accent)' }} />
                    {f}
                  </li>
                ))}
              </ul>
              <Link href={isLoggedIn && p.href === '/signup' ? '/chat' : p.href}
                className={p.featured ? 'cta-primary w-full justify-center' : 'cta-secondary w-full justify-center'}>
                {p.cta}
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── FAQ ──────────────────────────────────────────────────────────────── */

const FAQ = [
  { q: 'Multiai چه فرقی با ChatGPT داره؟', a: 'Multiai یه پلتفرم یکپارچه‌ست — به بهترین مدل‌های هوش مصنوعی دنیا (DeepSeek, Mistral, Tencent, MiMo و...) از یک پنل دسترسی دارید، با قیمت ریالی و بدون نیاز به VPN.' },
  { q: 'آیا نیاز به VPN دارم؟', a: 'خیر. تمام ارتباطات از طریق زیرساخت اختصاصی و داخلی مسیریابی میشه. بدون فیلترشکن، بدون قطعی.' },
  { q: 'هزینه استفاده چقدره؟', a: 'تعرفه‌ها بر اساس مدل متفاوته. هزینه دقیق رو قبل از ارسال هر درخواست می‌بینید. مدل Tencent HY-3 برای شروع رایگانه.' },
  { q: 'اطلاعات من امنه؟', a: 'بله. تمام ارتباطات رمزنگاری شده (TLS 1.3)، داده‌ها روی سرورهای اختصاصی ذخیره میشن.' },
  { q: 'چطور API key بسازم؟', a: 'بعد از ثبت‌نام، از پنل کاربری > بخش «کلید API» یک کلید جدید بسازید. endpoint ما با OpenAI-compatible هست.' },
  { q: 'Smart Mode چیه؟', a: 'Smart Mode محتوای پیام شما رو تحلیل میکنه و بهترین مدل رو بر اساس موجودی کیف پول انتخاب میکنه. همیشه cheapest capable model.' },
]

function FAQSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(null)
  const { ref, visible } = useReveal()
  return (
    <section ref={ref} className="py-24 md:py-32">
      <div className="max-w-2xl mx-auto px-6">
        <div className="text-center mb-16">
          <p className="section-eyebrow">سوالات متداول</p>
          <h2 className="section-heading">هر سوالی دارید، جوابش اینجاست</h2>
        </div>
        <div className="reveal" style={{ opacity: visible ? 1 : undefined, transform: visible ? 'none' : undefined }}>
          {FAQ.map((item, i) => {
            const isOpen = openIndex === i
            return (
              <div key={item.q} className="faq-item">
                <button className="faq-trigger" onClick={() => setOpenIndex(isOpen ? null : i)} aria-expanded={isOpen}>
                  <span>{item.q}</span>
                  <Icon name="arrowRight" size={14}
                    style={{ color: 'var(--text-muted)', transition: 'transform 300ms ease', transform: isOpen ? 'rotate(90deg)' : 'none' }} />
                </button>
                <div className={`faq-answer${isOpen ? ' open' : ''}`}>
                  <div><p>{item.a}</p></div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}

/* ── CTA Banner ───────────────────────────────────────────────────────── */

function CTABanner({ isLoggedIn }: { isLoggedIn: boolean }) {
  const { ref, visible } = useReveal(0.2)
  return (
    <section ref={ref} className="py-24 md:py-32" style={{ background: 'rgba(129,140,248,0.02)' }}>
      <div className="max-w-2xl mx-auto px-6 text-center">
        <div className="capability-card reveal" style={{
          padding: '3rem', borderRadius: '1.5rem',
          borderColor: 'rgba(129,140,248,0.12)',
          opacity: visible ? 1 : undefined, transform: visible ? 'none' : undefined
        }}>
          <h2 className="section-heading mb-4">آماده شروع هستید؟</h2>
          <p className="mb-8" style={{ color: 'var(--text-muted)' }}>
            همین حالا ثبت‌نام کنید و به پیشرفته‌ترین مدل‌های هوش مصنوعی دسترسی پیدا کنید.
            بدون VPN، بدون تحریم، با قیمت ریالی.
          </p>
          <Link href={isLoggedIn ? '/chat' : '/signup'} className="cta-primary">
            {isLoggedIn ? 'رفتن به چت' : 'شروع رایگان — ۳۰ ثانیه'}
            <Icon name="arrowRight" size={16} />
          </Link>
        </div>
      </div>
    </section>
  )
}

/* ── Page ──────────────────────────────────────────────────────────────── */

export default function LandingPage() {
  const { user } = useAuth()
  const isLoggedIn = !!user
  const [models, setModels] = useState<ModelCatalogItem[]>([])
  const [modelsLoaded, setModelsLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch('/api/catalog/models')
      .then(r => r.json())
      .then((d: CatalogResponse) => { if (!cancelled) setModels(d?.data ?? []) })
      .catch(err => { console.error('Failed to fetch catalog:', err) })
      .finally(() => { if (!cancelled) setModelsLoaded(true) })
    return () => { cancelled = true }
  }, [])

  const modelCount = modelsLoaded ? modelCountLabel(models) : 'در حال بارگذاری...'

  return (
    <div className="landing-v6">
      <Hero isLoggedIn={isLoggedIn} modelCount={modelCount} />
      <PlatformMarquee />
      <Stats modelCount={modelCount} />
      <Capabilities />
      <HowItWorks />
      <Pricing isLoggedIn={isLoggedIn} modelCount={modelCount} />
      <FAQSection />
      <CTABanner isLoggedIn={isLoggedIn} />
      <footer className="text-center py-12 text-sm" style={{ color: 'var(--text-muted)', borderTop: '1px solid rgba(255,255,255,0.03)' }}>
        <p>Multiai — پلتفرم کامل هوش مصنوعی فارسی</p>
      </footer>
    </div>
  )
}