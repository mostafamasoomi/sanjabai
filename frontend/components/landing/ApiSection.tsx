'use client'

import { useState } from 'react'
import { Icon } from '../ui/Icon'
import { Reveal } from './Reveal'
import { CheckGlyph, ForwardArrow } from './primitives'
import { API_BASE_URL, API_POINTS, CODE_SAMPLES } from './content'

const LANGUAGES = Object.keys(CODE_SAMPLES)

function CopyButton({ value }: { value: string }) {
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
      aria-label={copied ? 'کپی شد' : 'کپی کردن نمونه کد'}
    >
      <Icon name={copied ? 'check' : 'copy'} size={16} />
    </button>
  )
}

export function ApiSection() {
  const [lang, setLang] = useState(LANGUAGES[0])
  const sample = CODE_SAMPLES[lang]

  return (
    <section className="lp-section">
      <div className="lp-container lp-split">
        <Reveal className="lp-split__copy">
          <span className="lp-eyebrow">برای توسعه‌دهندگان</span>
          <h2 className="lp-title">یک endpoint، همه‌ی مدل‌ها</h2>
          <p className="lp-lead">
            آدرس پایه را به <span className="lp-latin">{API_BASE_URL}</span> تغییر دهید.
            همین. کتابخانه‌های رسمی OpenAI بدون هیچ تغییر دیگری کار می‌کنند.
          </p>

          <ul className="lp-checklist">
            {API_POINTS.map((point) => (
              <li key={point}>
                <CheckGlyph />
                {point}
              </li>
            ))}
          </ul>

          <a href="/developer" className="lp-btn lp-btn--secondary">
            مطالعه‌ی مستندات
            <ForwardArrow />
          </a>
        </Reveal>

        <Reveal delay={120}>
          <div className="lp-code">
            <div className="lp-code__head" role="tablist" aria-label="زبان نمونه کد">
              {LANGUAGES.map((name) => (
                <button
                  key={name}
                  type="button"
                  role="tab"
                  className="lp-code__tab"
                  aria-selected={lang === name}
                  onClick={() => setLang(name)}
                >
                  {name}
                </button>
              ))}
              <CopyButton value={sample} />
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
