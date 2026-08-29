'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useLang } from '../LanguageToggle'
import { CheckGlyph, ForwardArrow, ProviderLogo } from './primitives'
import { EnamadBadge } from './EnamadBadge'
import { heroContent } from './content'
import { heroStrings } from './Hero.strings'
import { useTilt } from './useTilt'
import { useScrollParallax } from './useScrollParallax'
import { Constellation } from './Constellation'
import { VortexIntro } from './VortexIntro'

const AURA_DEPTHS = [
  { depth: 0.06, baseX: '-50%' },
  { depth: 0.1, baseX: '0' },
  { depth: 0.15, baseX: '0' },
] as const

/* ── Rotating headline word ───────────────────────────────────────────────── */

function Rotator() {
  const lang = useLang()
  const { rotation } = heroContent(lang)
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const timer = window.setInterval(
      () => setIndex((i) => (i + 1) % rotation.length),
      2600,
    )
    return () => window.clearInterval(timer)
  }, [rotation.length])

  return (
    <span className="lp-hero__rotator">
      <span className="lp-hero__rotator-sizer" aria-hidden="true">
        {rotation.map((word) => (
          <span key={word}>{word}</span>
        ))}
      </span>
      <span key={index} className="lp-hero__rotator-word">
        {rotation[index]}
      </span>
    </span>
  )
}

/* ── Product preview ──────────────────────────────────────────────────────── */

function ProductPreview() {
  const lang = useLang()
  const s = heroStrings(lang)
  const { previewThreads } = heroContent(lang)
  const [active, setActive] = useState(0)
  const thread = previewThreads[active]
  const previewRef = useRef<HTMLDivElement>(null)
  useTilt(previewRef, true, 5)

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

          <div className="lp-preview__tabs" role="tablist" aria-label={s.previewTabsAria}>
            {previewThreads.map((t, i) => (
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
            <span className="lp-msg__avatar">{s.youLabel}</span>
            <p className="lp-msg__bubble">{thread.question}</p>
          </div>

          <div className="lp-msg lp-msg--ai">
            <span className="lp-msg__avatar">
              {thread.logo ? <ProviderLogo src={thread.logo} size={15} /> : s.unknownAvatar}
            </span>
            <p className="lp-msg__bubble">
              {typed}
              {!done && <span className="lp-msg__caret" aria-hidden="true" />}
            </p>
          </div>

          <div className="lp-preview__meta">
            <span>
              {s.modelLabel} <b dir="ltr">{thread.label}</b>
            </span>
            <span>{s.costNote}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Hero ─────────────────────────────────────────────────────────────────── */

export function Hero() {
  const lang = useLang()
  const s = heroStrings(lang)
  const { trust } = heroContent(lang)
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
    <section className="lp-hero lp-hero--with-vortex" ref={sectionRef}>
      {/* Dynamic Tornado Background */}
      <div className="lp-hero__vortex-bg">
        <VortexIntro />
      </div>

      <div className="lp-grid-lines" aria-hidden="true" />
      <div className="lp-aura" aria-hidden="true">
        <span className="lp-aura__blob" ref={blobRef1} />
        <span className="lp-aura__blob" ref={blobRef2} />
        <span className="lp-aura__blob" ref={blobRef3} />
        <Constellation />
      </div>

      <div className="lp-container lp-hero__content-wrap">
        <div className="lp-hero__inner">
          <a href="/signup" className="lp-pill lp-pill--glow">
            <span className="lp-pill__dot" />
            <span className="lp-pill__text">{s.pillText}</span>
          </a>

          <h1 className="lp-hero__title">
            <span className="lp-hero__title-highlight">{s.titleHighlight}</span>
            <br />
            <Rotator />
          </h1>

          <p className="lp-hero__lead">{s.lead}</p>

          <EnamadBadge compact />

          <div className="lp-hero__actions">
            <a href="/signup" className="lp-btn lp-btn--primary lp-btn--lg lp-btn--glow">
              {s.ctaPrimary}
              <ForwardArrow />
            </a>
            <a href="/models" className="lp-btn lp-btn--secondary lp-btn--lg">
              {s.ctaSecondary}
            </a>
          </div>

          <ul className="lp-hero__trust">
            {trust.map((item) => (
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
