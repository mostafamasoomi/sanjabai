'use client'

import { useState } from 'react'
import { Icon } from '../ui/Icon'
import { useLang } from '../LanguageToggle'
import { Reveal } from './Reveal'
import { CheckGlyph, ForwardArrow } from './primitives'
import { API_BASE_URL, apiContent } from './content'
import { apiSectionStrings } from './ApiSection.strings'

function CopyButton({ value, copyLabel, copiedLabel }: { value: string; copyLabel: string; copiedLabel: string }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      // Clipboard is unavailable over plain HTTP and in some embedded
      // browsers; the sample is selectable, so failing quietly is fine.
    }
  }

  return (
    <button
      type="button"
      className="lp-icon-btn lp-code__copy"
      onClick={copy}
      aria-label={copied ? copiedLabel : copyLabel}
    >
      <Icon name={copied ? 'check' : 'copy'} size={16} />
    </button>
  )
}

export function ApiSection() {
  const lang = useLang()
  const s = apiSectionStrings(lang)
  const content = apiContent(lang)
  // Renamed from `lang`/`setLang`: this is the code-sample language picker
  // (Python/JavaScript/cURL), unrelated to the UI language toggle above —
  // sharing the name would shadow `useLang()`'s result inside this component.
  const [codeLang, setCodeLang] = useState(Object.keys(content.codeSamples)[0])
  const sample = content.codeSamples[codeLang]

  return (
    <section className="lp-section">
      <div className="lp-container lp-split">
        <Reveal className="lp-split__copy">
          <span className="lp-eyebrow">{s.eyebrow}</span>
          <h2 className="lp-title">{s.title}</h2>
          <p className="lp-lead">
            {s.leadBefore}
            <span className="lp-latin">{API_BASE_URL}</span>
            {s.leadAfter}
          </p>

          <ul className="lp-checklist">
            {content.points.map((point) => (
              <li key={point}>
                <CheckGlyph />
                {point}
              </li>
            ))}
          </ul>

          <a href="/developer" className="lp-btn lp-btn--secondary">
            {s.docsLinkLabel}
            <ForwardArrow />
          </a>
        </Reveal>

        <Reveal delay={120}>
          <div className="lp-code">
            <div className="lp-code__head" role="tablist" aria-label={s.codeTabAria}>
              {Object.keys(content.codeSamples).map((name) => (
                <button
                  key={name}
                  type="button"
                  role="tab"
                  className="lp-code__tab"
                  aria-selected={codeLang === name}
                  onClick={() => setCodeLang(name)}
                >
                  {name}
                </button>
              ))}
              <CopyButton value={sample} copyLabel={s.copyLabel} copiedLabel={s.copiedLabel} />
            </div>
            {/* dir="ltr" lives on .lp-code__body so code is never reordered by
                the surrounding RTL document. */}
            <pre className="lp-code__body">
              <code>{sample}</code>
            </pre>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
