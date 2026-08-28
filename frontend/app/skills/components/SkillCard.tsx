'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { type Skill, CATEGORY_BADGES, categoryLabel, renderStars, getAverageRating } from '../types'
import { skillCardStrings } from './SkillCard.strings'

/* ═══════════════════════════════════════════════════════════════
   Skill Card
   ═══════════════════════════════════════════════════════════════ */

export default function SkillCard({ skill, onUse }: { skill: Skill; onUse: (s: Skill) => void }) {
  const lang = useLang()
  const s = skillCardStrings(lang)
  const f = fmt(lang)
  const avg = getAverageRating(skill)

  return (
    <div
      className="card card-interactive"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.625rem',
        padding: '1.25rem',
        animationDelay: '0ms',
      }}
    >
      {/* Header: category badge + usage */}
      <div className="flex items-center justify-between">
        <span
          className={`badge ${CATEGORY_BADGES[skill.category] || 'aurora-cap-default'}`}
          style={{ fontSize: '0.6875rem' }}
        >
          {categoryLabel(skill.category, lang)}
        </span>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
          <Icon name="user" size={12} />
          {s.usageCount(f.num(skill.usage_count))}
        </span>
      </div>

      {/* Title */}
      <h2 style={{ fontSize: 'var(--fs-md)', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.5 }}>
        {skill.title_fa || skill.title}
      </h2>

      {/* Description preview */}
      <p
        style={{
          fontSize: '0.8125rem',
          color: 'var(--text-secondary)',
          lineHeight: 1.6,
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}
      >
        {skill.description_fa || skill.description}
      </p>

      {/* Tags */}
      {skill.tags && skill.tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>
          {skill.tags.slice(0, 4).map((tag) => (
            <span
              key={tag}
              style={{
                fontSize: '0.6875rem',
                padding: '0.125rem 0.5rem',
                borderRadius: 'var(--radius-full)',
                background: 'var(--bg-elevated)',
                color: 'var(--text-muted)',
                border: '1px solid var(--border)',
              }}
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Rating + action */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.25rem' }}>
        <div className="flex items-center gap-1">
          {renderStars(avg, 12)}
          {skill.rating_count > 0 && (
            <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginRight: '0.25rem' }}>
              ({f.num(skill.rating_count)})
            </span>
          )}
        </div>
        <button
          className="btn btn-primary btn-sm"
          onClick={() => onUse(skill)}
          style={{ fontSize: '0.8125rem', padding: '0.375rem 0.875rem' }}
        >
          <Icon name="send" size={14} />
          {s.useAction}
        </button>
      </div>

      {/* Clarifies /use is a single one-shot run, unlike permanent activation
          via SkillActivationPanel — the two are easy to confuse and the
          wrong assumption costs the user money either direction. */}
      <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'end', lineHeight: 1.4 }}>
        {s.useOnceHint}
      </p>
    </div>
  )
}
