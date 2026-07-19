'use client'

import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '@/lib/auth'
import { Icon } from '@/components/ui/Icon'
import { modelCountLabel } from '@/lib/claims'
import { type ModelCatalogItem, type CatalogResponse } from '@/types/catalog'
import VortexParticles from '@/components/VortexParticles'


/* Landing v7 — motion.page STRUCTURE DNA
   Asymmetric hero · constellation · bento · API stage · three doors
   Real capabilities only. No SaaS feature-grid. No fake metrics. */

function useReveal(threshold = 0.12) {
  const ref = useRef<HTMLDivElement>(null)
  const [on, setOn] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) setOn(true)
    }, { threshold })
    obs.observe(el)
    return () => obs.disconnect()
  }, [threshold])
  return { ref, on }
}

function useScrollProgress(ref: React.RefObject<HTMLElement | null>) {
  const [progress, setProgress] = useState(0)
  useEffect(() => {
    let frame = 0
    const update = () => {
      const el = ref.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      const range = Math.max(el.offsetHeight - window.innerHeight, 1)
      setProgress(Math.min(1, Math.max(0, -rect.top / range)))
    }
    const onScroll = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(update) }
    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => { cancelAnimationFrame(frame); window.removeEventListener('scroll', onScroll); window.removeEventListener('resize', onScroll) }
  }, [ref])
  return progress
}

/** Sets --scroll (0..1 over hero height) and --page-scroll (0..1 over doc) on <html>.
 *  Drives VortexParticles focus + hero parallax. rAF-throttled. */
function usePageScroll() {
  useEffect(() => {
    let frame = 0
    const update = () => {
      const y = window.scrollY
      const hero = document.querySelector('.hero') as HTMLElement | null
      const heroH = hero?.offsetHeight || window.innerHeight
      const docRange = Math.max(document.documentElement.scrollHeight - window.innerHeight, 1)
      document.documentElement.style.setProperty('--scroll', String(Math.min(1, y / heroH)))
      document.documentElement.style.setProperty('--page-scroll', String(Math.min(1, y / docRange)))
      frame = 0
    }
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(update) }
    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => { cancelAnimationFrame(frame); window.removeEventListener('scroll', onScroll); window.removeEventListener('resize', onScroll) }
  }, [])
}

const MODELS_STRIP = [
  'DeepSeek V4', 'Mistral Large', 'Tencent HY-3', 'MiMo Pro',
  'Smart Mode', 'OpenAI API', 'RAG', 'Zarinpal',
]

const CHIPS = [
  'چت چندمدلی',
  'Smart Mode',
  'API سازگار با OpenAI',
  'RAG و فایل',
  'حافظه و اسکیلز',
  'تسک زمان‌بندی',
  'مقایسه مدل',
  'کیف‌پول ریالی',
]

function Hero({ isLoggedIn, modelCount }: { isLoggedIn: boolean; modelCount: string }) {
  return (
    <section className="hero" aria-label="Hero">
      <VortexParticles />
      <div className="hero-orbit" aria-hidden="true">
        <span className="hero-orbit-ring hero-orbit-ring-a" />
        <span className="hero-orbit-ring hero-orbit-ring-b" />
        <span className="hero-orbit-core" />
        <span className="hero-orbit-beam" />
      </div>
      <div className="hero-parallax" style={{ transform: 'translateY(calc(var(--scroll, 0) * 90px)) scale(calc(1 - var(--scroll, 0) * 0.05))', opacity: 'calc(1 - var(--scroll, 0) * 0.55)' }}>
        <div className="shell hero-grid">
          <div className="hero-copy">
            <div className="announcement entrance-item">
              <span className="chip">NEW</span>
              Smart Mode — مدل مناسب را خودش انتخاب میکند
            </div>
          <h1 className="display entrance-item">
            یک درگاه.
            <br />
            <span className="mark">همه مدلها.</span>
          </h1>
          <p className="lede entrance-item" style={{ marginTop: '1.25rem' }}>
            چت چندمدلی، API سازگار با OpenAI، پرداخت ریالی با زرینپال —
            بدون VPN. از یک workspace به پیشرفتهترین مدلها وصل شوید.
          </p>
          <div className="hero-actions entrance-item">
            <Link href={isLoggedIn ? '/chat' : '/signup'} className="btn-primary">
              {isLoggedIn ? 'شروع چت' : 'شروع رایگان'}
              <Icon name="arrowRight" size={16} />
            </Link>
            <Link href="/developer" className="btn-secondary">
              مستندات API
            </Link>
          </div>
          <div className="hero-trust entrance-item">
            <span><Icon name="check" size={14} style={{ color: 'var(--accent-teal)' }} />{modelCount}</span>
            <span><Icon name="check" size={14} style={{ color: 'var(--accent-teal)' }} />بدون VPN</span>
            <span><Icon name="check" size={14} style={{ color: 'var(--accent-teal)' }} />پرداخت ریالی</span>
          </div>
        </div>

        <div className="stage entrance-item" aria-hidden="true" style={{ animationDelay: '0.92s' }}>
          <div className="stage-bar">
            <span className="stage-dot" />
            <span className="stage-dot" />
            <span className="stage-dot" />
            <span style={{ marginInlineStart: '0.5rem' }}>multiai · chat</span>
            <span style={{ marginInlineStart: 'auto', color: 'var(--accent-teal)' }}>Smart Mode</span>
          </div>
          <div className="stage-body">
            <div className="chat-line">
              <div className="chat-bubble user">
                یک endpoint OpenAI-compatible برای اپم می‌خوام که با کیف‌پول ریالی کار کنه.
              </div>
            </div>
            <div className="chat-line">
              <div className="chat-bubble bot">
                <div className="model-badge">
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent-teal)' }} />
                  routed · deepseek-v4-pro
                </div>
                endpoint شما با OpenAI سازگار است. کلید API بسازید، base_url را عوض کنید،
                هزینه هر درخواست قبل از ارسال نمایش داده می‌شود.
              </div>
            </div>
            <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {['chat', 'api', 'rag', 'wallet'].map((t) => (
                <span key={t} style={{
                  fontSize: '0.7rem',
                  color: 'var(--text-dim)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 999,
                  padding: '0.2rem 0.55rem',
                }}>{t}</span>
              ))}
            </div>
          </div>
        </div>
      </div>
      </div>
    </section>
  )
}

function Marquee() {
  const items = [...MODELS_STRIP, ...MODELS_STRIP]
  return (
    <div className="marquee" role="marquee" aria-label="Supported AI models">
      <div className="marquee-track">
        {items.map((m, i) => (
          <span key={`${m}-${i}`} className="marquee-item">{m}</span>
        ))}
      </div>
    </div>
  )
}

function ScrollRoutingStage({ isLoggedIn }: { isLoggedIn: boolean }) {
  const sectionRef = useRef<HTMLElement>(null)
  const progress = useScrollProgress(sectionRef)
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduced(mq.matches)
    update(); mq.addEventListener?.('change', update)
    return () => mq.removeEventListener?.('change', update)
  }, [])
  const step = reduced ? 1 : Math.min(3, Math.floor(progress * 4))
  const steps = [
    { label: '۱ · دریافت', title: 'درخواست وارد می‌شود', body: 'چت، فایل یا API — فرمت مهم نیست؛ نقطه ورود یکی است.', color: 'var(--accent-blue)' },
    { label: '۲ · فهم', title: 'Smart Mode مسئله را می‌خواند', body: 'دسته، پیچیدگی و موجودی کیف‌پول را برای این turn بررسی می‌کند.', color: 'var(--accent-pink)' },
    { label: '۳ · انتخاب', title: 'مدل مناسب route می‌شود', body: 'ارزان‌ترین مدل توانا انتخاب می‌شود؛ بدون انتخاب دستی و حدس.', color: 'var(--accent-violet)' },
    { label: '۴ · پاسخ', title: 'نتیجه در همان workspace', body: 'پاسخ را در چت، stream API یا task زمان‌بندی‌شده تحویل بگیرید.', color: 'var(--accent-teal)' },
  ]
  const active=steps[step]
  const nodes=[{x:16,y:68,label:'chat'},{x:16,y:30,label:'file'},{x:50,y:50,label:'smart'},{x:84,y:30,label:'model'},{x:84,y:70,label:'api'}]
  const routeTargets = ['chat', 'smart', 'model', 'api']
  return <section ref={sectionRef} className="routing-scroll-section">
    <div className="routing-sticky shell-wide">
      <div className="routing-copy">
        <p className="eyebrow">Scroll to route</p>
        <h2 className="display">از درخواست تا پاسخ، <span className="mark">زنده.</span></h2>
        <p className="lede">غلتک را بچرخانید. مسیر Smart Mode را قدم‌به‌قدم ببینید.</p>
        <div className="routing-steps">{steps.map((s,i)=><div key={s.label} className={`routing-step ${i===step?'active':''}`} style={{'--step-color':s.color} as React.CSSProperties}><span>{s.label}</span><strong>{s.title}</strong></div>)}</div>
        <Link href={isLoggedIn?'/chat':'/signup'} className="text-link routing-cta">همین حالا امتحانش کن <Icon name="arrowRight" size={14}/></Link>
      </div>
      <div className="routing-stage" style={{'--routing-progress':progress,'--routing-color':active.color} as React.CSSProperties}>
        <div className="routing-stage-beam" aria-hidden="true" />
        <div className="routing-stage-grid" aria-hidden="true"/>
        <svg className="routing-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path d="M16 68 C29 68,35 50,50 50 S70 30,84 30"/><path d="M16 30 C29 30,35 50,50 50 S70 70,84 70"/><path className="routing-trace" pathLength="1" d="M16 68 C29 68,35 50,50 50 S70 30,84 30" style={{strokeDashoffset:1-Math.max(progress*1.7,.02)}}/></svg>
        {nodes.map((n,i)=><div key={n.label} className={`routing-node ${i===step?'active':''}`} style={{left:`${n.x}%`,top:`${n.y}%`}}><span className="routing-node-dot"/><small>{n.label}</small></div>)}
        <div className="routing-state-pill"><i /> {routeTargets[step]} selected</div>
        <div className="routing-readout" aria-live="polite"><span className="routing-live"><i/> LIVE ROUTE</span><strong>{active.title}</strong><p>{active.body}</p><div className="routing-progress"><span style={{transform:`scaleX(${Math.max(progress,.04)})`}}/></div><code>progress {Math.round(progress*100)}%</code></div>
      </div>
    </div>
  </section>
}

function Constellation() {
  const { ref, on } = useReveal()
  return (
    <section className="section" ref={ref} aria-label="Capabilities">
      <div className="shell">
        <div className={`section-head reveal ${on ? 'on' : ''}`}>
          <p className="eyebrow">کل جعبه ابزار</p>
          <h2 className="section-title">قدرت‌هایی که واقعاً دارید</h2>
          <p className="lede" style={{ marginTop: '0.85rem' }}>
            نه لیست بازاریابی — قابلیت‌های زنده پنل: چت، API، مسیریابی هوشمند، فایل، حافظه و اتوماسیون.
          </p>
        </div>
        <div className={`constellation reveal ${on ? 'on' : ''}`} style={{ transitionDelay: '80ms' }}>
          {CHIPS.map((c) => (
            <span key={c} className="chip"><i />{c}</span>
          ))}
        </div>
      </div>
    </section>
  )
}

function SmartSplit({ isLoggedIn }: { isLoggedIn: boolean }) {
  const { ref, on } = useReveal()
  return (
    <section className="section" ref={ref} style={{ background: 'rgba(255,255,255,0.01)' }}>
      <div className={`shell split reveal ${on ? 'on' : ''}`}>
        <div>
          <p className="eyebrow">Smart Mode</p>
          <h2 className="section-title">مدل را تو انتخاب نکن — مسیر هوشمند انتخاب میکند.</h2>
          <p className="lede" style={{ marginTop: '1rem' }}>
            پیام را تحلیل میکند، دسته را تشخیص می‌دهد (کد، استدلال، خلاقیت، ساده)
            و ارزان‌ترین مدل توانا را با توجه به موجودی کیف‌پول برمی‌گزیند.
          </p>
          <div style={{ marginTop: '1.5rem' }}>
            <Link href={isLoggedIn ? '/chat' : '/signup'} className="text-link">
              امتحان در چت
              <Icon name="arrowRight" size={14} />
            </Link>
          </div>
        </div>
        <div className="stage">
          <div className="stage-bar">
            <span className="stage-dot" />
            <span className="stage-dot" />
            <span className="stage-dot" />
            <span style={{ marginInlineStart: '0.5rem' }}>routing · live</span>
          </div>
          <div className="stage-body" style={{ direction: 'ltr', textAlign: 'left', fontFamily: 'ui-monospace, monospace', fontSize: '0.78rem', lineHeight: 1.7, color: 'var(--text-dim)' }}>
            <div><span style={{ color: 'var(--accent-pink)' }}>input</span>: &quot;refactor this FastAPI endpoint&quot;</div>
            <div><span style={{ color: 'var(--accent-violet)' }}>category</span>: code</div>
            <div><span style={{ color: 'var(--accent-teal)' }}>selected</span>: deepseek-v4-pro</div>
            <div><span style={{ color: 'var(--accent-blue)' }}>headers</span>: X-Smart-Model · X-Smart-Category</div>
            <div style={{ marginTop: '0.75rem', color: 'var(--text-muted)' }}>// cheapest capable model for this turn</div>
          </div>
        </div>
      </div>
    </section>
  )
}

function BentoTheater() {
  const { ref, on } = useReveal()
  return (
    <section className="section" ref={ref}>
      <div className="shell">
        <div className={`section-head reveal ${on ? 'on' : ''}`}>
          <p className="eyebrow">Product theater</p>
          <h2 className="section-title">نشان بده. ادعا نکن.</h2>
          <p className="lede" style={{ marginTop: '0.85rem' }}>
            هر کارت یک سطح واقعی محصول است — نه آیکون بالای سه خط توضیح.
          </p>
        </div>
        <div className={`bento reveal ${on ? 'on' : ''}`} style={{ transitionDelay: '60ms' }}>
          <article className="bento-card wide featured">
            <div className="bento-visual">
              <div className="hi">POST /v1/chat/with-file</div>
              <div>accept: .pdf .txt .md .csv .json · max 10MB</div>
              <div className="vi">→ extract · inject context · stream answer</div>
            </div>
            <p className="eyebrow" style={{ marginBottom: 0 }}>RAG / FILE</p>
            <h3>فایل را آپلود کنید، مدل استناد میکند</h3>
            <p>PDF و متن را می‌خواند، به عنوان context تزریق میکند و در همان مکالمه پاسخ می‌دهد.</p>
          </article>

          <article className="bento-card wide">
            <div className="bento-visual">
              <div className="pi">memory.auto_extract</div>
              <div>facts ≤ 3 / conversation</div>
              <div className="hi">skills.marketplace · clone · rate · run</div>
            </div>
            <p className="eyebrow" style={{ marginBottom: 0 }}>MEMORY & SKILLS</p>
            <h3>حافظه + اسکیلز</h3>
            <p>حقایق مهم مکالمه ذخیره می‌شود. اسکیل‌های آماده را clone کنید و با متغیر اجرا کنید.</p>
          </article>

          <article className="bento-card">
            <div className="bento-visual">
              <div className="vi">cron: 0 9 * * *</div>
              <div>delivery: dashboard | telegram</div>
              <div className="hi">tasks.run_now()</div>
            </div>
            <p className="eyebrow" style={{ marginBottom: 0 }}>SCHEDULE</p>
            <h3>تسک زمان‌بندی</h3>
            <p>پرامپت‌های تکراری را زمان‌بندی کنید و نتیجه را در پنل یا تلگرام بگیرید.</p>
          </article>

          <article className="bento-card">
            <div className="bento-visual">
              <div>model A ──┐</div>
              <div className="hi">         ├─ compare</div>
              <div>model B ──┘</div>
              <div className="pi">latency · tokens · cost</div>
            </div>
            <p className="eyebrow" style={{ marginBottom: 0 }}>COMPARE</p>
            <h3>مقایسه مدل</h3>
            <p>دو مدل موازی؛ زمان، توکن و هزینه کنار هم.</p>
          </article>

          <article className="bento-card">
            <div className="bento-visual">
              <div className="hi">baseURL: /v1</div>
              <div>Authorization: Bearer ***
              </div>
              <div className="vi">chat.completions.create()</div>
            </div>
            <p className="eyebrow" style={{ marginBottom: 0 }}>API</p>
            <h3>OpenAI-compatible</h3>
            <p>کلید بسازید، base_url را عوض کنید — SDKهای رایج کار می‌کنند.</p>
          </article>
        </div>
      </div>
    </section>
  )
}

function ApiStage() {
  const { ref, on } = useReveal()
  const snippet = `from openai import OpenAI

client = OpenAI(
  api_key="sk-...",
  base_url="https://your-host/v1",
)

client.chat.completions.create(
  model="deepseek-v4-pro",
  messages=[{"role":"user","content":"سلام"}],
)`
  return (
    <section className="section" ref={ref} style={{ background: 'rgba(48,218,220,0.02)' }}>
      <div className={`shell split reveal ${on ? 'on' : ''}`}>
        <div className="stage">
          <div className="stage-bar">
            <span className="stage-dot" />
            <span className="stage-dot" />
            <span className="stage-dot" />
            <span style={{ marginInlineStart: '0.5rem' }}>sdk · openai-compatible</span>
          </div>
          <pre className="stage-body" style={{
            margin: 0,
            direction: 'ltr',
            textAlign: 'left',
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            fontSize: '0.78rem',
            lineHeight: 1.7,
            color: 'var(--text-dim)',
            whiteSpace: 'pre-wrap',
          }}>{snippet}</pre>
        </div>
        <div>
          <p className="eyebrow">OpenAI-compatible API</p>
          <h2 className="section-title">همان SDK. endpoint ما.</h2>
          <p className="lede" style={{ marginTop: '1rem' }}>
            برای اپ‌ها و agentها: completions استریم و غیر استریم، مدیریت کلید API،
            و صورتحساب توکنی با نمایش هزینه. دسترسی بدون VPN.
          </p>
          <div style={{ marginTop: '1.5rem', display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
            <Link href="/developer" className="btn-secondary">رفتن به Developer</Link>
            <Link href="/pricing" className="text-link">
              دیدن تعرفه‌ها
              <Icon name="arrowRight" size={14} />
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}

function LocalReality() {
  const { ref, on } = useReveal()
  return (
    <section className="section" ref={ref}>
      <div className="shell">
        <div className={`section-head reveal ${on ? 'on' : ''}`}>
          <p className="eyebrow">واقعیت محلی</p>
          <h2 className="section-title">بدون VPN. پرداخت ریالی.</h2>
        </div>
        <div className={`facts reveal ${on ? 'on' : ''}`} style={{ transitionDelay: '70ms' }}>
          <div className="fact">
            <h3>دسترسی مستقیم</h3>
            <p>
              زیرساخت اختصاصی طوری طراحی شده که بدون فیلترشکن به چت و API برسید —
              همان چیزی که برای کار روزمره در ایران لازم است.
            </p>
          </div>
          <div className="fact">
            <h3>کیف‌پول زرین‌پال</h3>
            <p>
              شارژ با تومان، موجودی شفاف، و نمایش هزینه درخواست وقتی قیمت مدل موجود باشد.
              بدون داستان ارزی پیچیده.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}

function ThreeDoors({ isLoggedIn }: { isLoggedIn: boolean }) {
  const { ref, on } = useReveal()
  return (
    <section className="section" ref={ref} style={{ background: 'rgba(175,71,255,0.03)' }}>
      <div className="shell">
        <div className={`section-head center reveal ${on ? 'on' : ''}`}>
          <p className="eyebrow">Architecture</p>
          <h2 className="section-title">یک موتور. سه در.</h2>
          <p className="lede" style={{ marginTop: '0.85rem' }}>
            همان مدل‌ها، سه ورودی: گفتگو، API، اتوماسیون.
          </p>
        </div>
        <div className={`doors reveal ${on ? 'on' : ''}`} style={{ transitionDelay: '80ms' }}>
          <div className="door featured">
            <div className="n">Door 01</div>
            <h3>گفتگو</h3>
            <p>چت چندمدلی، Smart Mode، مقایسه، آپلود فایل و حافظه — برای کار روزمره.</p>
            <Link href={isLoggedIn ? '/chat' : '/signup'}>ورود به چت →</Link>
          </div>
          <div className="door">
            <div className="n">Door 02</div>
            <h3>API</h3>
            <p>OpenAI-compatible برای اپ‌ها و agentها. کلید بسازید و base_url را عوض کنید.</p>
            <Link href="/developer">مستندات →</Link>
          </div>
          <div className="door">
            <div className="n">Door 03</div>
            <h3>اتوماسیون</h3>
            <p>تسک‌های زمان‌بندی‌شده، اسکیلز و تحویل به داشبورد یا تلگرام.</p>
            <Link href={isLoggedIn ? '/tasks' : '/signup'}>تسک‌ها →</Link>
          </div>
        </div>
      </div>
    </section>
  )
}

function FinalCta({ isLoggedIn }: { isLoggedIn: boolean }) {
  const { ref, on } = useReveal(0.2)
  return (
    <section className="final" ref={ref} aria-label="Get started">
      <div className={`shell reveal ${on ? 'on' : ''}`}>
        <h2 className="display">شروع کن — مدل‌ها منتظرند.</h2>
        <p className="lede">
          ثبت‌نام سریع، پرداخت ریالی، دسترسی بدون VPN.
          اگر از قبل حساب دارید، مستقیم بروید سراغ چت یا API.
        </p>
        <div className="final-actions">
          <Link href={isLoggedIn ? '/chat' : '/signup'} className="btn-primary">
            {isLoggedIn ? 'رفتن به چت' : 'ساخت حساب'}
            <Icon name="arrowRight" size={16} />
          </Link>
          <Link href="/models" className="btn-secondary">کاتالوگ مدل‌ها</Link>
        </div>
      </div>
    </section>
  )
}

export default function LandingPage() {
  const { user } = useAuth()
  const isLoggedIn = !!user
  const [models, setModels] = useState<ModelCatalogItem[]>([])
  const [modelsLoaded, setModelsLoaded] = useState(false)

  usePageScroll()

  useEffect(() => {
    let cancelled = false
    fetch('/api/catalog/models')
      .then((r) => r.json())
      .then((d: CatalogResponse) => {
        if (!cancelled) setModels(d?.data ?? [])
      })
      .catch((err) => console.error('Failed to fetch catalog:', err))
      .finally(() => {
        if (!cancelled) setModelsLoaded(true)
      })
    return () => { cancelled = true }
  }, [])

  const modelCount = modelsLoaded ? modelCountLabel(models) : 'در حال بارگذاری…'

  return (
    <div className="landing-v7">

      <Hero isLoggedIn={isLoggedIn} modelCount={modelCount} />
      <Marquee />
      <ScrollRoutingStage isLoggedIn={isLoggedIn} />
      <Constellation />
      <SmartSplit isLoggedIn={isLoggedIn} />
      <BentoTheater />
      <ApiStage />
      <LocalReality />
      <ThreeDoors isLoggedIn={isLoggedIn} />
      <FinalCta isLoggedIn={isLoggedIn} />
      <footer className="foot">
        <div className="shell">Multiai — درگاه هوش مصنوعی فارسی</div>
      </footer>
    </div>
  )
}
