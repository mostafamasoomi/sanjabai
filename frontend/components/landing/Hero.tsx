'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckGlyph, ForwardArrow, ProviderLogo } from './primitives'
import { HERO_ROTATION, HERO_TRUST, PREVIEW_THREADS } from './content'
import { useTilt } from './useTilt'
import { useScrollParallax } from './useScrollParallax'
import { Constellation } from './Constellation'

/** Each blob drifts at its own fraction of scroll speed — the closer the
 * fraction is to 0, the farther back the layer reads as sitting. `baseX`
 * mirrors each blob's own CSS `translate` x-component (blob 1 is centered
 * via `inset-inline-start: 50%` + `translate: -50% 0`), since the parallax
 * hook writes the whole `translate` property and would otherwise wipe it. */
const AURA_DEPTHS = [
  { depth: 0.06, baseX: '-50%' },
  { depth: 0.1, baseX: '0' },
  { depth: 0.15, baseX: '0' },
] as const

/* ── Rotating headline word ───────────────────────────────────────────────── */

function Rotator() {
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const timer = window.setInterval(
      () => setIndex((i) => (i + 1) % HERO_ROTATION.length),
      2600,
    )
    return () => window.clearInterval(timer)
  }, [])

  return (
    <span className="lp-hero__rotator">
      {/* Invisible stack sizes the box to the widest word, so swapping the
          visible word below never reflows the headline. */}
      <span className="lp-hero__rotator-sizer" aria-hidden="true">
        {HERO_ROTATION.map((word) => (
          <span key={word}>{word}</span>
        ))}
      </span>
      {/* Only the current word is ever actually mounted -- a key-based
          remount plus a CSS entrance animation, not a cross-fade of several
          stacked, simultaneously-opaque elements -- so two different words
          can never be visible at once. */}
      <span key={index} className="lp-hero__rotator-word">
        {HERO_ROTATION[index]}
      </span>
    </span>
  )
}

/* ── Product preview ──────────────────────────────────────────────────────── */

function ProductPreview() {
  const [active, setActive] = useState(0)
  const thread = PREVIEW_THREADS[active]
  const previewRef = useRef<HTMLDivElement>(null)
  useTilt(previewRef, true, 5)

  // Types the answer out when the reader switches model tabs.
  //
  // The initial state is the *complete* answer, so the server-rendered HTML
  // carries real content and a reader without JavaScript still sees a finished
  // conversation. That makes the first mount a special case: replaying the
  // animation there would blank the bubble that was just painted and retype
  // it, which reads as a flash. So the first run only arms the ref, and the
  // typewriter starts from the first genuine tab change onward.
  const [typed, setTyped] = useState(thread.answer)
  const timerRef = useRef<number>()
  const mounted = useRef(false)

  useEffect(() => {
    window.clearInterval(timerRef.current)

    if (!mounted.current) {
      mounted.current = true
      return
    }

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setTyped(thread.answer)
      return
    }

    setTyped('')
    let i = 0
    timerRef.current = window.setInterval(() => {
      i += 2
      setTyped(thread.answer.slice(0, i))
      if (i >= thread.answer.length) window.clearInterval(timerRef.current)
    }, 18)

    return () => window.clearInterval(timerRef.current)
  }, [thread])

  const done = typed.length >= thread.answer.length

  return (
    <div className="lp-preview-stack">
      <span className="lp-preview-ghost lp-preview-ghost--2" aria-hidden="true" />
      <span className="lp-preview-ghost lp-preview-ghost--1" aria-hidden="true" />
      <div className="lp-preview" ref={previewRef}>
        <div className="lp-preview__sheen" aria-hidden="true" />
        <div className="lp-preview__bar">
          <span className="lp-preview__dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>

          <div className="lp-preview__tabs" role="tablist" aria-label="انتخاب مدل">
            {PREVIEW_THREADS.map((t, i) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                className="lp-preview__tab"
                aria-selected={i === active}
                onClick={() => setActive(i)}
              >
                {t.logo && <ProviderLogo src={t.logo} size={14} />}
                <span dir="ltr">{t.label}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="lp-preview__body">
          <div className="lp-msg lp-msg--user">
            <span className="lp-msg__avatar">شما</span>
            <p className="lp-msg__bubble">{thread.question}</p>
          </div>

          <div className="lp-msg lp-msg--ai">
            <span className="lp-msg__avatar">
              {thread.logo ? <ProviderLogo src={thread.logo} size={15} /> : '؟'}
            </span>
            {/* No aria-live here on purpose: announcing a decorative typewriter
                two characters at a time would flood a screen reader. The bubble
                is ordinary content and is read when the user reaches it. */}
            <p className="lp-msg__bubble">
              {typed}
              {!done && <span className="lp-msg__caret" aria-hidden="true" />}
            </p>
          </div>

          {/* Deliberately no latency or per-message price here: any number we
              printed would be invented. The real figures are computed per
              request and shown in the product itself. */}
          <div className="lp-preview__meta">
            <span>
              مدل: <b dir="ltr">{thread.label}</b>
            </span>
            <span>هزینه‌ی تخمینی هر پیام، پیش از ارسال در خود چت نمایش داده می‌شود</span>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Hero ─────────────────────────────────────────────────────────────────── */

export function Hero() {
  // Tilt is attached to the section, not .lp-aura itself: the aura has
  // pointer-events: none (so it never steals clicks from the content sitting
  // on top of it) and so can never *receive* the pointermove that would
  // drive it. Setting --tx/--ty here and reading them on .lp-aura (a plain
  // inherited custom property) lets the background read depth from the
  // cursor while the foreground content stays perfectly still and legible.
  const sectionRef = useRef<HTMLElement>(null)
  useTilt(sectionRef, true, 2.5)

  const blobRef1 = useRef<HTMLSpanElement>(null)
  const blobRef2 = useRef<HTMLSpanElement>(null)
  const blobRef3 = useRef<HTMLSpanElement>(null)
  const blobLayers = useMemo(
    () => [
      { ref: blobRef1, ...AURA_DEPTHS[0] },
      { ref: blobRef2, ...AURA_DEPTHS[1] },
      { ref: blobRef3, ...AURA_DEPTHS[2] },
    ],
    [],
  )
  useScrollParallax(sectionRef, blobLayers)

  return (
    <section className="lp-hero" ref={sectionRef}>
      {/* Ambient layers sit behind everything via z-index: -1 on .lp-aura. */}
      <div className="lp-grid-lines" aria-hidden="true" />
      <div className="lp-aura" aria-hidden="true">
        <span className="lp-aura__blob" ref={blobRef1} />
        <span className="lp-aura__blob" ref={blobRef2} />
        <span className="lp-aura__blob" ref={blobRef3} />
        <Constellation />
      </div>

      <div className="lp-container">
        <div className="lp-hero__inner">
          <a href="/signup" className="lp-pill">
            <span className="lp-pill__dot" />
            ثبت‌نام رایگان — بدون کارت اعتباری
          </a>

          <h1 className="lp-hero__title">
            ۲۳ مدل هوش مصنوعی،
            <Rotator />
          </h1>

          <p className="lp-hero__lead">
            با DeepSeek، Mistral، Gemini، Llama و ۱۹ مدل دیگر در یک فضای کاری فارسی کار
            کنید. عامل بسازید، خروجی‌ها را مقایسه کنید و همه را با یک API به محصول خودتان
            وصل کنید — با پرداخت به تومان و بدون اشتراک ماهانه.
          </p>

          <div className="lp-hero__actions">
            <a href="/signup" className="lp-btn lp-btn--primary lp-btn--lg">
              شروع رایگان
              <ForwardArrow />
            </a>
            <a href="/models" className="lp-btn lp-btn--secondary lp-btn--lg">
              مشاهده‌ی مدل‌ها
            </a>
          </div>

          <ul className="lp-hero__trust">
            {HERO_TRUST.map((item) => (
              <li key={item}>
                <CheckGlyph size={13} />
                {item}
              </li>
            ))}
          </ul>
        </div>

        <ProductPreview />
      </div>
    </section>
  )
}
