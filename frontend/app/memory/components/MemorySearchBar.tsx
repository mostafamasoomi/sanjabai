'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { memorySearchBarStrings } from './MemorySearchBar.strings'

/* ═══════════════════════════════════════════════════════════════
   Search bar. Split out of page.tsx verbatim -- no behaviour change.
   ═══════════════════════════════════════════════════════════════ */

export function MemorySearchBar({
  searchQuery,
  onSearch,
}: {
  searchQuery: string
  onSearch: (value: string) => void
}) {
  const lang = useLang()
  const s = memorySearchBarStrings(lang)

  return (
    <div style={{ position: 'relative', marginBottom: 16 }}>
      <Icon
        name="search"
        size={16}
        style={{
          position: 'absolute',
          right: 12,
          top: '50%',
          transform: 'translateY(-50%)',
          color: 'var(--text-muted)',
        }}
      />
      <input
        value={searchQuery}
        onChange={(e) => onSearch(e.target.value)}
        placeholder={s.searchPlaceholder}
        className="input"
        style={{ width: '100%', paddingRight: 36 }}
      />
      {searchQuery && (
        <button
          onClick={() => onSearch('')}
          style={{
            position: 'absolute',
            left: 12,
            top: '50%',
            transform: 'translateY(-50%)',
            background: 'none',
            border: 'none',
            padding: 4,
            cursor: 'pointer',
            display: 'flex',
          }}
        >
          <Icon name="close" size={14} className="text-muted" />
        </button>
      )}
    </div>
  )
}
