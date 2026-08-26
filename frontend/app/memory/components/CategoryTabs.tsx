'use client'

import { useLang } from '@/components/LanguageToggle'
import { categories } from '../memoryTypes'

/* ═══════════════════════════════════════════════════════════════
   Category filter tabs. Split out of page.tsx verbatim -- no
   behaviour change.
   ═══════════════════════════════════════════════════════════════ */

export function CategoryTabs({
  activeCategory,
  onSelect,
}: {
  activeCategory: string
  onSelect: (cat: string) => void
}) {
  const lang = useLang()
  const cats = categories(lang)

  return (
    <div
      style={{
        display: 'flex',
        gap: 6,
        marginBottom: 20,
        overflowX: 'auto',
        paddingBottom: 4,
      }}
    >
      {cats.map((cat) => (
        <button
          key={cat.key}
          onClick={() => onSelect(cat.key)}
          className={activeCategory === cat.key ? 'btn btn-primary btn-sm' : 'btn btn-ghost btn-sm'}
          style={{
            whiteSpace: 'nowrap',
            fontSize: 13,
            borderRadius: 'var(--radius-md)',
          }}
        >
          {cat.label}
        </button>
      ))}
    </div>
  )
}
