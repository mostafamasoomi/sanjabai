'use client'

import { Icon } from '@/components/ui/Icon'
import { SectionHeader, Field } from './shared'

/* ═══════════════════════════════════════════════════════════════════════════
   About — moved verbatim out of AdminPanel.tsx (page === 'about').
   All state and handlers still live in AdminPanel; this component is purely
   presentational.
   ═══════════════════════════════════════════════════════════════════════════ */

interface AboutSectionProps {
  abTitle: string
  setAbTitle: (v: string) => void
  abBody: string
  setAbBody: (v: string) => void
  saveAbout: () => void
}

export default function AboutSection({ abTitle, setAbTitle, abBody, setAbBody, saveAbout }: AboutSectionProps) {
  return (
    <div className="space-y-6">
      <SectionHeader title="درباره ما" subtitle="محتوای صفحه درباره ما" />

      <div className="admin-card">
        <div className="space-y-4">
          <Field label="عنوان">
            <input className="input w-full" value={abTitle} onChange={(e) => setAbTitle(e.target.value)} placeholder="درباره Sanjabai" />
          </Field>
          <Field label="متن">
            <textarea
              className="input w-full min-h-[200px] resize-y leading-relaxed"
              value={abBody}
              onChange={(e) => setAbBody(e.target.value)}
              placeholder="متن درباره ما به فارسی..."
            />
          </Field>
        </div>
        <button className="btn mt-4" onClick={saveAbout}>
          <Icon name="check" size={16} />
          <span>ذخیره</span>
        </button>
      </div>
    </div>
  )
}
