'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { dangerZoneSectionStrings } from './DangerZoneSection.strings'

export default function DangerZoneSection() {
  const lang = useLang()
  const s = dangerZoneSectionStrings(lang)

  return (
    <div className="card profile-danger-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Icon name="warning" size={16} className="text-danger" />
        <h2 style={{ fontSize: 15, fontWeight: 700, color: 'var(--danger)' }}>
          {s.title}
        </h2>
      </div>
      <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
        {s.intro}
      </p>
      <button className="btn btn-danger" disabled style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <Icon name="trash" size={14} />
        {s.deleteAccount}
      </button>
    </div>
  )
}
