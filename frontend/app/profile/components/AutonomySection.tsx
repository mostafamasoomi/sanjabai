'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { AUTONOMY_LEVELS } from '../types'
import { autonomySectionStrings } from './AutonomySection.strings'
import Hint from '@/components/Hint'

type AutonomySectionProps = {
  autonomyLevel: string
  setAutonomyLevel: (v: string) => void
}

export default function AutonomySection({ autonomyLevel, setAutonomyLevel }: AutonomySectionProps) {
  const lang = useLang()
  const s = autonomySectionStrings(lang)

  return (
    <div className="card profile-section-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="rocket" size={16} className="text-accent" />
        <h2 className="card-title">
          {s.title}
        </h2>
        <Hint id="profile.autonomy" />
      </div>
      <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
        {s.intro}
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {AUTONOMY_LEVELS.map((level) => (
          <div
            key={level.value}
            onClick={() => setAutonomyLevel(level.value)}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 12,
              padding: '14px 16px',
              borderRadius: 10,
              border: `2px solid ${autonomyLevel === level.value ? 'var(--accent)' : 'var(--border)'}`,
              background: autonomyLevel === level.value ? 'var(--accent-bg)' : 'transparent',
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
          >
            <div style={{
              width: 20, height: 20, borderRadius: '50%', marginTop: 2, flexShrink: 0,
              border: `2px solid ${autonomyLevel === level.value ? 'var(--accent)' : 'var(--border)'}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {autonomyLevel === level.value && (
                <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--accent)' }} />
              )}
            </div>
            <div className="flex-1">
              <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)', marginBottom: 4 }}>
                {lang === 'fa' ? level.label_fa : level.label_en}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                {lang === 'fa' ? level.desc_fa : level.desc_en}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
