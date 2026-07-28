'use client'

import { useEffect, useState } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import VortexBackground from '@/components/VortexBackground'
import WaterTrailBackground from '@/components/WaterTrailBackground'
import MeshGradientBackground from '@/components/MeshGradientBackground'
import PhysicsBoxes from '@/components/PhysicsBoxes'
import './motion-effects.css'

/* ════════════════════════════════════════════════════════════════════════════
   Data — motion.page reference, rebranded to MultiAI
   ════════════════════════════════════════════════════════════════════════════ */

const TRICKS = [
  { icon: '/icons/scroll.svg', title: 'Scroll\nAnimations' },
  { icon: '/icons/transition.svg', title: 'Page\nTransitions' },
  { icon: '/icons/gesture.svg', title: 'Hover &\nGestures' },
  { icon: '/icons/timeline.svg', title: 'Timeline\nSequencing' },
  { icon: '/icons/cursor.svg', title: 'Custom\nCursors' },
  { icon: '/icons/stagger.svg', title: 'Stagger\nEffects' },
  { icon: '/icons/svg-icon.svg', title: 'SVG &\nDrawSVG' },
  { icon: '/icons/splittext.svg', title: 'SplitText\nEffects' },
]

const LOGOS = [
  { name: 'WordPress', src: '/logos/wordpress.svg' },
  { name: 'Webflow', src: '/logos/webflow.svg' },
  { name: 'Shopify', src: '/logos/shopify.svg' },
  { name: 'React', src: '/logos/react.svg' },
  { name: 'Vue', src: '/logos/vue.svg' },
  { name: 'Astro', src: '/logos/astro.svg' },
  { name: 'Elementor', src: '/logos/elementor.svg' },
  { name: 'Oxygen', src: '/logos/oxygen.svg' },
  { name: 'Bricks', src: '/logos/bricks.svg' },
  { name: 'Wix', src: '/logos/wix.svg' },
  { name: 'HTML5', src: '/logos/html5.svg' },
  { name: 'Claude', src: '/logos/claude.svg' },
  { name: 'Next.js', src: '/logos/nextjs.svg' },
  { name: 'Svelte', src: '/logos/svelte.svg' },
  { name: 'Tailwind', src: '/logos/tailwind.svg' },
  { name: 'Nuxt', src: '/logos/nuxt.svg' },
  { name: 'Angular', src: '/logos/angular.svg' },
  { name: 'Framer', src: '/logos/framer.svg' },
  { name: 'Squarespace', src: '/logos/squarespace.svg' },
]

const CODE_TABS: Record<string, string> = {
  Animation: `from({ opacity: 0, y: 40 })
  .to({ opacity: 1, y: 0 })
  .duration(0.6)
  .ease('power2.out')
  .onScroll({ scrub: true })`,
  Timeline: `from({ opacity: 0, scale: 0.9 })
  .to({ opacity: 1, scale: 1 })
  .duration(0.8)
  .ease('power3.out')
  .stagger(0.1)`,
  Stagger: `.from('.card', {
    opacity: 0,
    y: 60,
    rotateX: 15
  })
  .duration(0.7)
  .stagger(0.05, {
    from: 'center'
  })`,
  SplitText: `SplitText.create('.heading', {
  type: 'chars,words'
})
.from(chars, {
  opacity: 0,
  y: 20,
  stagger: 0.02
})`,
  DrawSVG: `gsap.from('.path', {
  drawSVG: '0%',
  duration: 1.5,
  ease: 'power2.inOut',
  scrollTrigger: {
    trigger: '.path',
    scrub: true
  }
})`,
}

const FEATURES_ROW1 = [
  { img: '/illustrations/hp-builder.webp', eyebrow: 'VISUAL BUILDER', title: 'Pick a thing. Make it move.', desc: 'Point at your live site, choose an element, set a trigger, and drag the timing. No code. No timeline jargon.' },
  { img: '/illustrations/hp-scroll.webp', eyebrow: 'SCROLL ANIMATIONS', title: 'Pin. Scrub. Parallax.', desc: 'Pinned sections, scroll-scrubbed timelines, layered parallax — the stuff that usually eats a week of JavaScript. Here it takes five clicks.' },
  { img: '/illustrations/hp-export.webp', eyebrow: 'ONE-CLICK DEPLOY', title: 'Go live with one line', desc: 'Hit deploy. You get a clean snippet you can paste anywhere — WordPress, Webflow, React, plain HTML. Done.' },
]

const FEATURES_ROW2 = [
  { img: '/illustrations/hp-builder-card.webp', eyebrow: 'THE BUILDER', title: 'Animate any site, visually', desc: 'Pick any element on your live page, choose a trigger, and drag the timing. If you can use Figma, you can use MultiAI.' },
  { img: '/illustrations/hp-canvas.webp', eyebrow: 'THE CANVAS', title: 'Shaders, without the math', desc: 'Canvas is a complete WebGPU visual production editor — with a real video timeline, not a folder of shader presets.' },
  { img: '/illustrations/hp-sdk.webp', eyebrow: 'THE SDK', title: 'The engine under it all', desc: 'One function, one object. Every visual the builder produces is pure SDK code — zero runtime, zero lock-in.' },
]

const CANVAS_ASSETS = [
  { name: 'Event Horizon', src: '/illustrations/canvas-event-horizon.webp' },
  { name: 'Nebula Plasma', src: '/illustrations/canvas-nebula-plasma.webp' },
  { name: 'Heatmap', src: '/illustrations/canvas-heatmap.webp' },
]

const TESTIMONIALS = [
  { text: '"Genial and perfect tool. MultiAI is the most incredible tool to create complex and amazing animations with less time and effort."', name: 'Andre Beltrame', avatar: '/avatars/andre-beltrame.jpeg' },
  { text: '"Brilliant and innovative. The next big thing in online animation. Very well crafted and very thought through."', name: 'Rene Brokop', avatar: '/avatars/rene-brokop.jpg' },
  { text: '"Once you dig and understand how the animations work, you start to see opportunities to make your website so much more interesting."', name: 'Jonathan Jernigan', avatar: '/avatars/jonathan-jernigan.jpg' },
]

const PRICING_PLANS = [
  { name: 'Builder', price: '€99', period: '/year', features: ['Visual builder', 'Unlimited projects', 'All SDK features', 'WordPress plugin', 'Priority support'] },
  { name: 'Canvas', price: '€149', period: '/year', features: ['Everything in Builder', 'Canvas editor', 'Shader library', 'WebGPU rendering', 'Export to any platform'] },
  { name: 'Bundle', price: '€199', period: '/year', features: ['Everything in Canvas', 'Builder + Canvas combined', 'Save €49/year', 'All future updates', 'Early access'] },
]

/* ════════════════════════════════════════════════════════════════════════════
   Components
   ════════════════════════════════════════════════════════════════════════════ */

function ArrowIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M1 11L11 1M11 1H4M11 1V8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function LogoIcon({ src, name }: { src: string; name: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) return <span style={{ fontSize: '0.8rem' }}>{name}</span>
  return <img src={src} alt={name} onError={() => setFailed(true)} />
}

/* ── MotionEffects ──────────────────────────────────────────────────── */
function MotionEffects() {
  useEffect(() => {
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced || typeof window === 'undefined') return

    gsap.registerPlugin(ScrollTrigger)

    // Hero camera progress (vortex + water trail)
    gsap.to({}, {
      scrollTrigger: {
        trigger: '.motion-hero',
        start: 'top top',
        end: 'bottom top',
        scrub: 1,
        onUpdate: (self: any) => {
          const p = self.progress
          document.documentElement.style.setProperty('--scroll-progress', String(p))
          if ((window as any).motionVortex) (window as any).motionVortex.setProgress(p)
        }
      }
    })

    // Reveal sections with stagger
    document.querySelectorAll('.motion-section')
      .forEach((el: any) => {
        gsap.from(el, {
          scrollTrigger: {
            trigger: el,
            start: 'top 88%',
            toggleClass: { targets: el, className: 'is-visible' },
          },
          y: 42,
          opacity: 0,
          scale: 0.985,
          duration: 0.8,
          ease: 'power2.out',
        })
      })

    // Engine door stagger
    document.querySelectorAll('.motion-engine-door').forEach((el: any, i: number) => {
      gsap.from(el, {
        scrollTrigger: {
          trigger: el.closest('.motion-engine-doors'),
          start: 'top 85%',
        },
        y: 30,
        opacity: 0,
        delay: i * 0.1,
        duration: 0.6,
        ease: 'power2.out',
      })
    })

    // Stats count-up
    document.querySelectorAll('.motion-stat-num').forEach((el: any) => {
      const text = el.textContent
      const target = parseFloat(text.replace(/[^0-9.]/g, '')) || 0
      const suffix = text.replace(/[0-9.]/g, '')
      gsap.from(el, {
        scrollTrigger: {
          trigger: el.closest('.motion-stats'),
          start: 'top 85%',
        },
        textContent: 0,
        duration: 1.2,
        ease: 'power2.out',
        snap: { textContent: 1 },
        modifiers: {
          textContent: (v: number) => {
            const n = Math.round(v * target)
            return n >= 1000 ? `${(n / 1000).toFixed(1)}k${suffix}` : `${n}${suffix}`
          }
        }
      })
    })

    // Feature card reveal
    document.querySelectorAll('.motion-feature-card').forEach((el: any, i: number) => {
      gsap.from(el, {
        scrollTrigger: {
          trigger: el.closest('.motion-features-grid'),
          start: 'top 85%',
        },
        y: 30,
        opacity: 0,
        delay: i * 0.08,
        duration: 0.7,
        ease: 'power2.out',
      })
    })

    ScrollTrigger.refresh()
    return () => ScrollTrigger.getAll().forEach((st: any) => st.kill())
  }, [])

  return null
}

/* ── Nav ────────────────────────────────────────────────────────────── */
function Nav() {
  const [scrolled, setScrolled] = useState(false)
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40)
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  return (
    <nav className={`motion-nav${scrolled ? ' motion-nav--scrolled' : ''}`}>
      <div className="motion-nav-inner">
        <a href="/" className="motion-nav-logo">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M4 4h6v6H4V4zm0 10h6v6H4v-6zm10-10h6v6h-6V4zm3 10h3v6h-3v-6z" fill="currentColor"/>
          </svg>
        </a>
        <div className="motion-nav-center">
          <a href="#builder">Builder</a>
          <a href="#canvas">Canvas</a>
          <a href="#stack">Platforms</a>
          <a href="#pricing">Plans</a>
          <a href="https://docs.multi-ai.com" target="_blank" rel="noopener">Docs</a>
        </div>
        <div className="motion-nav-right">
          <a href="#" className="motion-nav-link">Log in</a>
          <a href="#" className="motion-nav-cta">Get Started</a>
        </div>
      </div>
    </nav>
  )
}

/* ── Hero ────────────────────────────────────────────────────────────── */
function Hero() {
  return (
    <section className="motion-hero">
      <MeshGradientBackground variant={0} />
      <MeshGradientBackground variant={1} />
      <VortexBackground />
      <WaterTrailBackground />
      <div className="motion-hero-content">
        <a href="#canvas" className="motion-hero-pill">
          NEW Canvas is here — the agent-native visual production studio
        </a>
        <h1>The complete animation stack.</h1>
        <p className="motion-hero-sub">
          Point at your live site, animate it visually, and walk away with clean, zero-dependency code. Scroll, hover, text, cursors — all of it.
        </p>
        <div className="motion-hero-actions">
          <a href="#" className="motion-btn motion-btn-primary">Start animating</a>
          <a href="#builder" className="motion-btn motion-btn-ghost">See it in action</a>
        </div>
      </div>
      <div className="motion-hero-strip">
        <div className="motion-strip-track">
          {[...LOGOS, ...LOGOS].map((m, i) => (
            <div key={i} className="motion-strip-chip">
              <LogoIcon src={m.src} name={m.name} />
              <span>{m.name}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── Tricks Grid ────────────────────────────────────────────────────── */
function TricksGrid() {
  return (
    <section className="motion-section">
      <div className="motion-section-inner">
        <h2 className="motion-section-title">The whole bag of tricks</h2>
        <div className="motion-tricks-grid">
          {TRICKS.map((t, i) => (
            <div key={i} className="motion-trick-card">
              <img src={t.icon} alt="" aria-hidden="true" />
              <span className="motion-trick-label">{t.title}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── Visual Builder + SDK ────────────────────────────────────────────── */
function BuilderSection() {
  const [tab, setTab] = useState('Animation')
  return (
    <section id="builder" className="motion-section motion-section-alt">
      <div className="motion-section-inner">
        <div className="motion-builder">
          <div className="motion-builder-text">
            <span className="motion-eyebrow">VISUAL BUILDER + SDK</span>
            <h3>You point and click.<br />It writes real code.</h3>
            <p className="motion-builder-p">Grab any element on your live page, choose a trigger, and set the timing. MultiAI writes the same SDK code a senior dev would, then hands it over.</p>
            <a href="#pricing" className="motion-btn motion-btn-ghost" style={{ marginTop: '0.5rem' }}>Explore plans <ArrowIcon /></a>
          </div>
          <div className="motion-builder-visual">
            <div className="motion-code-block">
              <div className="motion-code-tabs">
                {Object.keys(CODE_TABS).map(name => (
                  <button key={name} className={tab === name ? 'active' : ''} onClick={() => setTab(name)}>
                    {name}
                  </button>
                ))}
              </div>
              <pre key={tab}>{CODE_TABS[tab]}</pre>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ── Feature Card ───────────────────────────────────────────────────── */
function FeatureCard({ img, eyebrow, title, desc }: { img: string; eyebrow: string; title: string; desc: string }) {
  return (
    <article className="motion-feature-card">
      <img src={img} alt="" className="motion-feature-img" />
      <span className="motion-eyebrow">{eyebrow}</span>
      <h3 className="motion-feature-title">{title}</h3>
      <p className="motion-feature-desc">{desc}</p>
    </article>
  )
}

/* ── Point. Click. Animate. ─────────────────────────────────────────── */
function PointClickAnimate() {
  return (
    <section className="motion-section">
      <div className="motion-section-inner">
        <span className="motion-eyebrow">VISUAL BUILDER</span>
        <h2 className="motion-section-title">Point. Click. Animate.</h2>
        <p className="motion-section-sub">Here&apos;s everything the builder does — point, click, animate, and ship.</p>
        <div className="motion-features-grid">
          {FEATURES_ROW1.map((f, i) => <FeatureCard key={i} {...f} />)}
        </div>
        <div className="motion-features-grid" style={{ marginTop: '1.5rem' }}>
          {FEATURES_ROW2.map((f, i) => <FeatureCard key={i} {...f} />)}
        </div>
      </div>
    </section>
  )
}

/* ── Canvas Showcase ─────────────────────────────────────────────────── */
function CanvasSection() {
  return (
    <section id="canvas" className="motion-section motion-canvas-showcase">
      <div className="motion-section-inner">
        <div className="motion-canvas-heading">
          <span className="motion-eyebrow">CANVAS · AGENT-NATIVE PRODUCTION</span>
          <h2 className="motion-section-title">Million-dollar assets made with Canvas.</h2>
          <p className="motion-section-sub">Canvas is a complete WebGPU visual production editor — with a real video timeline, not a folder of shader presets.</p>
          <a href="#" className="motion-btn motion-btn-primary">Create with Canvas · €149/year</a>
        </div>
        <div style={{ position: 'relative', marginBottom: '3rem', borderRadius: 'var(--radius)', border: '1px solid var(--border)', overflow: 'hidden' }}>
          <img src="/illustrations/canvas-between-two-infinities.webp" alt="MultiAI Canvas editing the Between Two Infinities composition" style={{ width: '100%', display: 'block' }} />
        </div>
        <div className="motion-canvas-gallery">
          {CANVAS_ASSETS.map(({ name, src }) => (
            <article key={name} className="motion-canvas-card">
              <img src={src} alt={name} />
              <h3>{name}</h3>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── Stack Grid ──────────────────────────────────────────────────────── */
function StackSection() {
  return (
    <section id="stack" className="motion-section motion-section-alt">
      <div className="motion-section-inner">
        <span className="motion-eyebrow">YOUR STACK, COVERED</span>
        <h2 className="motion-section-title">Plays nice with<br />everything</h2>
        <p className="motion-section-sub">
          WordPress, React, Astro, Webflow, Shopify, plain HTML — MultiAI drops into whatever you&apos;ve already built. Your stack stays exactly as it is.
        </p>
        <div className="motion-stack-grid">
          {LOGOS.map((s, i) => (
            <div key={i} className="motion-stack-item">
              <img src={s.src} alt={s.name} />
              <span>{s.name}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── Timeline Editor ────────────────────────────────────────────────── */
function TimelineSection() {
  return (
    <section className="motion-section">
      <div className="motion-section-inner motion-timeline">
        <div className="motion-timeline-text">
          <span className="motion-eyebrow">VISUAL TIMELINE EDITOR</span>
          <h3>Every from and to,<br />laid out on a timeline</h3>
          <p>Drag, stretch, and stack animation entries like clips in a video editor. Every change previews live on your actual site. When it looks right, it is right.</p>
          <a href="https://docs.multi-ai.com" target="_blank" rel="noopener" className="motion-btn motion-btn-ghost">Learn more <ArrowIcon /></a>
        </div>
        <div className="motion-timeline-code">
          <div className="motion-code-block" style={{ padding: '1.5rem' }}>
            <div style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: '0.85rem', marginBottom: '1rem' }}>
              hero-entrance <span style={{ color: 'var(--text-muted)' }}>0.00s / 4.00s</span>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {['from', 'opacity', 'y', 'duration', 'ease', 'stagger'].map((label, i) => (
                <div key={i} style={{
                  padding: '0.5rem 1rem',
                  borderRadius: 'var(--radius-sm)',
                  background: i === 0 ? 'rgba(175,71,255,0.1)' : 'rgba(255,255,255,0.04)',
                  border: '1px solid var(--border)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.8rem',
                  color: i === 0 ? 'rgb(255,91,222)' : 'var(--text-muted)',
                }}>{label}</div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ── SDK API ─────────────────────────────────────────────────────────── */
function SDKSection() {
  return (
    <section className="motion-section motion-section-alt">
      <div className="motion-section-inner motion-timeline">
        <div className="motion-timeline-text">
          <span className="motion-eyebrow">DECLARATIVE SDK</span>
          <h3>One function. One object.<br />That&apos;s the whole API.</h3>
          <p>from, to, duration, ease — pass a plain object and you&apos;re done. You&apos;ll have it memorized before your coffee cools.</p>
          <a href="https://docs.multi-ai.com" target="_blank" rel="noopener" className="motion-btn motion-btn-ghost">Learn more <ArrowIcon /></a>
        </div>
        <div className="motion-timeline-code">
          <pre className="motion-code-block">{`from: { opacity: 0, y: 40 },
to: { opacity: 1, y: 0 },
duration: 0.6,
ease: 'power2.out',
}).onScroll({ scrub: true });`}</pre>
        </div>
      </div>
    </section>
  )
}

/* ── Stagger & Orchestration ────────────────────────────────────────── */
function StaggerSection() {
  return (
    <section className="motion-section">
      <div className="motion-section-inner motion-timeline">
        <div className="motion-timeline-text">
          <span className="motion-eyebrow">STAGGER & ORCHESTRATION</span>
          <h3>Move 500 elements<br />like they&apos;re one</h3>
          <p>Cascade from the center, ripple from the edges, or randomize across a grid. It stays smooth when the element count gets silly.</p>
          <a href="https://docs.multi-ai.com" target="_blank" rel="noopener" className="motion-btn motion-btn-ghost">Learn more <ArrowIcon /></a>
        </div>
        <div className="motion-timeline-code">
          <pre className="motion-code-block">{`from('.card', {
  opacity: 0,
  y: 60,
  rotateX: 15,
  stagger: {
    each: 0.05,
    from: 'center',
    grid: [20, 25]
  }
}).duration(0.7)`}</pre>
        </div>
      </div>
    </section>
  )
}

/* ── Composable Triggers ────────────────────────────────────────────── */
function TriggersSection() {
  const triggers = [
    { icon: '⬆', label: 'Scroll' },
    { icon: '👆', label: 'Hover' },
    { icon: '🔄', label: 'Click' },
    { icon: '👁', label: 'View' },
    { icon: '⏸', label: 'Pause' },
    { icon: '▶', label: 'Play' },
    { icon: '🔁', label: 'Loop' },
    { icon: '⚡', label: 'Custom' },
  ]
  return (
    <section className="motion-section motion-section-alt">
      <div className="motion-section-inner">
        <span className="motion-eyebrow">COMPOSABLE TRIGGERS</span>
        <h2 className="motion-section-title">Eight trigger types —<br />mix them however you like</h2>
        <div className="motion-tricks-grid" style={{ marginTop: '3rem' }}>
          {triggers.map((t, i) => (
            <div key={i} className="motion-trick-card">
              <span style={{ fontSize: '2rem' }}>{t.icon}</span>
              <span className="motion-trick-label">{t.label}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── SplitText ───────────────────────────────────────────────────────── */
function SplitTextSection() {
  return (
    <section className="motion-section">
      <div className="motion-section-inner motion-timeline">
        <div className="motion-timeline-text">
          <span className="motion-eyebrow">SPLITTEXT</span>
          <h3>Split, flip, scramble, mask —<br />text that performs</h3>
          <p>Break any text into characters, words, or lines — then animate each one individually with the same ease and timing you already know.</p>
          <a href="https://docs.multi-ai.com" target="_blank" rel="noopener" className="motion-btn motion-btn-ghost">Learn more <ArrowIcon /></a>
        </div>
        <div className="motion-timeline-code">
          <pre className="motion-code-block">{`SplitText.create('.heading', {
  type: 'chars,words'
})
.from(chars, {
  opacity: 0,
  y: 20,
  stagger: 0.02
})`}</pre>
        </div>
      </div>
    </section>
  )
}

/* ── Engine Doors ────────────────────────────────────────────────────── */
function EngineSection() {
  return (
    <section className="motion-section motion-section-alt">
      <div className="motion-section-inner">
        <h2 className="motion-section-title">One engine,<br />three doors</h2>
        <p className="motion-section-sub">
          One animation engine, three ways to drive it — a full desktop studio, a one-click WordPress plugin, or the raw SDK. Every path produces the same output.
        </p>
        <div className="motion-engine-doors">
          <div className="motion-engine-door">
            <span className="motion-eyebrow">THE BUILDER</span>
            <h4>Animate Everything</h4>
            <p>The full visual builder for macOS, Windows, and Linux. Point, click, animate, deploy.</p>
            <a href="#" className="motion-btn motion-btn-ghost" style={{ marginTop: '1rem', fontSize: '0.85rem' }}>Download the app <ArrowIcon /></a>
          </div>
          <div className="motion-engine-door">
            <span className="motion-eyebrow">WORDPRESS PLUGIN</span>
            <h4>Animate Everything</h4>
            <p>Install the plugin, open any page, and start animating. No export, no code — it just works.</p>
            <a href="#" className="motion-btn motion-btn-ghost" style={{ marginTop: '1rem', fontSize: '0.85rem' }}>Install plugin <ArrowIcon /></a>
          </div>
          <div className="motion-engine-door">
            <span className="motion-eyebrow">THE SDK</span>
            <h4>Animate Everything</h4>
            <p>One import, one function call. Full control from any framework, any build tool, any stack.</p>
            <a href="#" className="motion-btn motion-btn-ghost" style={{ marginTop: '1rem', fontSize: '0.85rem' }}>npm i @motion.page/sdk <ArrowIcon /></a>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ── Testimonials ────────────────────────────────────────────────────── */
function TestimonialsSection() {
  return (
    <section className="motion-section">
      <div className="motion-section-inner">
        <h2 className="motion-section-title">Kind words from<br />people who ship.</h2>
        <div className="motion-testimonials">
          {TESTIMONIALS.map((t, i) => (
            <div key={i} className="motion-testimonial">
              {t.avatar && <img src={t.avatar} alt={t.name} className="motion-test-avatar" />}
              <p className="motion-test-text">{t.text}</p>
              <div className="motion-test-meta">
                <strong>{t.name}</strong>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── Pricing ────────────────────────────────────────────────────────── */
function PricingSection() {
  const [annual, setAnnual] = useState(true)
  return (
    <section id="pricing" className="motion-section motion-section-alt">
      <div className="motion-section-inner">
        <h2 className="motion-section-title">Pick your creative weapon.</h2>
        <p className="motion-section-sub">Animations, shaders, or both — flat pricing, no per-seat math.</p>
        <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginBottom: '2.5rem' }}>
          <button
            onClick={() => setAnnual(false)}
            className={annual ? 'motion-btn motion-btn-ghost' : 'motion-btn motion-btn-primary'}
            style={{ fontSize: '13.44px', padding: '7px 20px', borderRadius: '9999px' }}
          >Monthly</button>
          <button
            onClick={() => setAnnual(true)}
            className={annual ? 'motion-btn motion-btn-primary' : 'motion-btn motion-btn-ghost'}
            style={{ fontSize: '13.44px', padding: '7px 20px', borderRadius: '9999px', background: annual ? 'rgba(255,255,255,0.1)' : undefined }}
          >Yearly −50%</button>
        </div>
        <div className="motion-pricing-grid">
          {PRICING_PLANS.map(plan => (
            <div key={plan.name} className="motion-pricing-card">
              <span className="motion-eyebrow">{plan.name}</span>
              <div className="motion-pricing-price">{plan.price}<span className="motion-pricing-period">{plan.period}</span></div>
              <ul className="motion-pricing-features">
                {plan.features.map(f => <li key={f}>{f}</li>)}
              </ul>
              <a href="#" className="motion-btn motion-btn-primary" style={{ background: 'rgba(255,91,222,0.08)', color: 'rgb(255,91,222)', fontSize: '13.44px' }}>
                Get instant access <ArrowIcon />
              </a>
              <div style={{ textAlign: 'center', marginTop: '0.5rem', fontSize: '10.08px', color: 'var(--text-dim)' }}>or try free for 7 days</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── CTA ────────────────────────────────────────────────────────────── */
function CTA() {
  return (
    <section className="motion-cta">
      <h2>Go on —<br />make something move.</h2>
      <p>Start with free credits. No credit card required.</p>
      <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
        <a href="#" className="motion-btn motion-btn-primary">Start animating</a>
        <a href="https://docs.multi-ai.com" target="_blank" rel="noopener" className="motion-btn" style={{ background: 'rgba(255,255,255,0.08)', color: 'rgb(186,188,210)', fontSize: '18.08px' }}>Read the docs</a>
      </div>
    </section>
  )
}

/* ── Footer ─────────────────────────────────────────────────────────── */
function Footer() {
  return (
    <footer className="motion-footer">
      <div className="motion-footer-inner">
        <div className="motion-footer-links">
          <div>
            <h4>Product</h4>
            <a href="#">Builder</a>
            <a href="#">Canvas</a>
            <a href="#">Platforms</a>
            <a href="#">Plans</a>
            <a href="#">Changelog</a>
          </div>
          <div>
            <h4>Resources</h4>
            <a href="#">Documentation</a>
            <a href="#">SDK Documentation</a>
            <a href="#">Builder Documentation</a>
            <a href="#">Status</a>
          </div>
          <div>
            <h4>Legal</h4>
            <a href="#">Terms of Service</a>
            <a href="#">Privacy Policy</a>
            <a href="#">EULA</a>
            <a href="#">Accessibility</a>
          </div>
        </div>
        <div className="motion-footer-bottom">
          <p>&copy; {new Date().getFullYear()} MultiAI — The complete animation stack. All rights reserved.</p>
        </div>
      </div>
    </footer>
  )
}

/* ════════════════════════════════════════════════════════════════════════════
   Page
   ════════════════════════════════════════════════════════════════════════════ */

export default function Home() {
  return (
    <>
      <div className="motion-grain" aria-hidden="true" />
      <MotionEffects />
      <Nav />
      <main>
        <Hero />
        <TricksGrid />
        <BuilderSection />
        <PointClickAnimate />
        <CanvasSection />
        <StackSection />
        <TimelineSection />
        <SDKSection />
        <StaggerSection />
        <TriggersSection />
        <SplitTextSection />
        <EngineSection />
        <PhysicsBoxes />
        <TestimonialsSection />
        <PricingSection />
        <CTA />
        <Footer />
      </main>
    </>
  )
}
