'use client'

import { useRef, useState } from 'react'
import { Icon } from '../ui/Icon'
import { Reveal } from './Reveal'
import { useTilt } from './useTilt'
import { ForwardArrow } from './primitives'
import { CAPABILITY_TABS, MEMORY_SAMPLES, DOCUMENT_TYPES, TASK_SAMPLES } from './content'

function MemoryPanel() {
  return (
    <ul className="lp-capshow__list">
      {MEMORY_SAMPLES.map((m) => (
        <li key={m.text} className="lp-capshow__row">
          <span>{m.text}</span>
          <span className="lp-capshow__tag">{m.category}</span>
        </li>
      ))}
    </ul>
  )
}

function DocumentsPanel() {
  return (
    <div className="lp-capshow__doctypes">
      {DOCUMENT_TYPES.map((d) => (
        <div key={d.ext} className="lp-capshow__doctype">
          <span className="lp-capshow__ext" dir="ltr">
            {d.ext}
          </span>
          <div>
            <strong>{d.label}</strong>
            <p>{d.desc}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

function TasksPanel() {
  return (
    <ul className="lp-capshow__list">
      {TASK_SAMPLES.map((t) => (
        <li key={t.title} className="lp-capshow__row">
          <div>
            <strong>{t.title}</strong>
            <p className="lp-capshow__meta">{t.schedule}</p>
          </div>
          <span className="lp-capshow__tag">{t.channel}</span>
        </li>
      ))}
    </ul>
  )
}

/**
 * A tabbed, deeper follow-up to the bento grid for the three capabilities
 * least obvious from a one-line card. Mirrors the hero's ProductPreview
 * interaction (tabs swap panel content) rather than inventing a new pattern.
 */
export function CapabilityShowcase() {
  const [active, setActive] = useState(0)
  const tab = CAPABILITY_TABS[active]
  const panelRef = useRef<HTMLDivElement>(null)
  useTilt(panelRef, true, 4)

  return (
    <section className="lp-section" id="capabilities">
      <div className="lp-container">
        <Reveal>
          <header className="lp-head">
            <span className="lp-eyebrow">فراتر از چت</span>
            <h2 className="lp-title">
              دستیاری که یادش می‌ماند، برایتان می‌سازد و به‌موقع کارش را انجام می‌دهد
            </h2>
            <p className="lp-lead">
              همه در همان فضای کاری — بدون افزونه‌ی جدا و بدون نرم‌افزار اضافه.
            </p>
          </header>
        </Reveal>

        <Reveal delay={80} className="lp-capshow">
          <div className="lp-capshow__tabs" role="tablist" aria-label="قابلیت‌ها">
            {CAPABILITY_TABS.map((t, i) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={i === active}
                className="lp-capshow__tabbtn"
                onClick={() => setActive(i)}
              >
                <span className="lp-capshow__tabicon">
                  <Icon name={t.icon} size={18} />
                </span>
                <strong>{t.tabLabel}</strong>
              </button>
            ))}
          </div>

          <div className="lp-capshow__panel" ref={panelRef}>
            <div className="lp-capshow__sheen" aria-hidden="true" />
            <div className="lp-capshow__panel-head">
              <h3>{tab.title}</h3>
              <p>{tab.desc}</p>
            </div>

            <div className="lp-capshow__panel-body">
              {tab.id === 'memory' && <MemoryPanel />}
              {tab.id === 'documents' && <DocumentsPanel />}
              {tab.id === 'tasks' && <TasksPanel />}
            </div>

            <a href={tab.href} className="lp-feature__link">
              {tab.linkLabel}
              <ForwardArrow size={13} />
            </a>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
