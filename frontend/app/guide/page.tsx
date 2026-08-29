'use client'

import Link from 'next/link'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { dirFor } from '@/lib/i18n'
import { TOUR_OPEN_EVENT } from '@/components/ProductTour'
import { productTourStrings } from '@/components/ProductTour.strings'
import { guideStrings, GUIDE_SECTION_ORDER, type GuideSection } from './guide.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   /guide — P-GUIDE (phase 8 پ-۴): the in-product education page.

   Deliberately the "minimum valuable" version from the phase-8 design doc:
   no CMS, no `guide_content` table, no admin editor (phase 6 already owns
   content editing; a second one here would be a duplicate). Six static
   sections, each answering the same four questions in the same order —
   content lives in guide.strings.ts, this file only lays it out.

   Zero backend calls, zero migration — every "what/when/cost/where" answer
   is static copy, checked against the actual billing code path once (see
   guide.strings.ts's header comment for the file-by-file trace) rather than
   fetched, because none of it is server state.
   ═══════════════════════════════════════════════════════════════════════════ */

type QuestionLabels = { what: string; when: string; cost: string; start: string }

function QuestionRow({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <div style={{ fontSize: '0.6875rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
        {label}
      </div>
      <p style={{ fontSize: '0.8125rem', lineHeight: 1.9, color: 'var(--text-secondary)' }}>
        {text}
      </p>
    </div>
  )
}

function SectionCard({ section, questionLabels }: { section: GuideSection; questionLabels: QuestionLabels }) {
  return (
    <div className="card" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
      <h2 style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--text-primary)' }}>
        {section.title}
      </h2>
      <QuestionRow label={questionLabels.what} text={section.what} />
      <QuestionRow label={questionLabels.when} text={section.when} />
      <QuestionRow label={questionLabels.cost} text={section.cost} />
      <div>
        <div style={{ fontSize: '0.6875rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '0.375rem' }}>
          {questionLabels.start}
        </div>
        <Link
          href={section.startHref}
          className="btn btn-sm btn-ghost no-underline"
          style={{ fontSize: '0.8125rem' }}
        >
          {section.startLabel}
          <Icon name="arrowLeft" size={14} />
        </Link>
      </div>
    </div>
  )
}

export default function GuidePage() {
  const lang = useLang()
  const s = guideStrings(lang)
  const t = productTourStrings(lang)

  // The cards below are the reference dictionary (what/when/cost per feature);
  // the interactive tour is the guided, workflow-first walkthrough. Offer it
  // up top so a reader who wants to be *shown* rather than *look up* has one
  // click to it. Dispatched as a window event that AppShell's tour listens for
  // (no shared context needed) — see ProductTour.tsx.
  const startTour = () => {
    if (typeof window !== 'undefined') window.dispatchEvent(new Event(TOUR_OPEN_EVENT))
  }

  return (
    <div className="flex flex-col gap-6" dir={dirFor(lang)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="page-title">{s.pageTitle}</h1>
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            {s.pageSubtitle}
          </p>
        </div>
        <button type="button" onClick={startTour} className="btn btn-primary btn-sm shrink-0">
          <Icon name="sparkles" size={16} />
          {t.guideCta}
        </button>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
          gap: '1rem',
        }}
      >
        {GUIDE_SECTION_ORDER.map((key) => (
          <SectionCard key={key} section={s.sections[key]} questionLabels={s.questionLabels} />
        ))}
      </div>
    </div>
  )
}
