'use client'

import Link from 'next/link'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { dirFor } from '@/lib/i18n'
import { tourAnchor } from '@/components/tour/anchors'
import { TEMPLATE_ORDER, templateApplyHref } from './templates'
import { templateStrings, templateGalleryStrings, type TourTemplate } from './templates.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   TemplateGallery — 14 structured starter recipes, each showcasing a
   high-productivity feature COMBINATION (assistant+skill+memory, file
   attach+chat, scheduled task, combo+smart mode, chat+ready prompt). Mounted
   on /guide, below the dictionary cards (guide/page.tsx owns placement).

   Carries `tourAnchor('guide.templates')` so the interactive tour (packet
   A/B territory, not this one) can spotlight the whole section — see
   components/tour/anchors.ts's header for why the attribute must come from
   `tourAnchor()` and not a raw `data-tour` string.

   Two apply mechanics per templates.ts: `navigate` links straight to the
   page where the user builds the recipe (e.g. /assistants/new); `chat-prefill`
   links to /chat?prompt=<encoded>, which already prefills and focuses the
   composer — zero backend work either way. `templateApplyHref` builds the
   href (and does the URL-encoding) at render time.
   ═══════════════════════════════════════════════════════════════════════════ */

function TemplateCard({ template, dir }: { template: TourTemplate; dir: 'rtl' | 'ltr' }) {
  const lang = useLang()
  const labels = templateGalleryStrings(lang)
  const href = templateApplyHref(template)
  const showSmartHint = template.apply.kind === 'chat-prefill' && template.apply.smartHint

  return (
    <div className="card" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <div className="flex items-center justify-between gap-2">
        <div className="card-icon">
          <Icon name={template.icon} size={18} />
        </div>
        <span
          className="text-xs px-2 py-0.5 rounded-full border border-[var(--border)] text-[var(--text-secondary)] bg-[var(--bg-surface)]"
          dir={dir}
        >
          {template.combo}
        </span>
      </div>

      <div>
        <h3 style={{ fontSize: '0.9375rem', fontWeight: 800, color: 'var(--text-primary)' }}>{template.title}</h3>
        <p style={{ fontSize: '0.8125rem', lineHeight: 1.8, color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
          {template.tagline}
        </p>
      </div>

      <details>
        <summary
          style={{
            fontSize: '0.75rem',
            fontWeight: 700,
            color: 'var(--text-muted)',
            cursor: 'pointer',
            userSelect: 'none',
          }}
        >
          {labels.ingredientsToggle}
        </summary>
        <ol style={{ fontSize: '0.8125rem', lineHeight: 1.9, color: 'var(--text-secondary)', marginTop: '0.5rem', paddingInlineStart: '1.1rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          {template.ingredients.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
          {showSmartHint && <li>{labels.smartHint}</li>}
        </ol>
      </details>

      <Link
        href={href}
        className="btn btn-sm btn-ghost no-underline"
        style={{ fontSize: '0.8125rem', alignSelf: 'flex-start', marginTop: 'auto' }}
      >
        {template.applyLabel}
        <Icon name="arrowLeft" size={14} />
      </Link>
    </div>
  )
}

export default function TemplateGallery() {
  const lang = useLang()
  const dir = dirFor(lang)
  const labels = templateGalleryStrings(lang)
  const s = templateStrings(lang)

  return (
    <section {...tourAnchor('guide.templates')} className="flex flex-col gap-4" dir={dir}>
      <div>
        <h2 className="page-title" style={{ fontSize: '1.125rem' }}>{labels.heading}</h2>
        <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
          {labels.subheading}
        </p>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
          gap: '1rem',
        }}
      >
        {TEMPLATE_ORDER.map((id) => (
          <TemplateCard key={id} template={s[id]} dir={dir} />
        ))}
      </div>
    </section>
  )
}
