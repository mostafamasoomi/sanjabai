'use client'

import { EmptyState } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { apiKeysSectionStrings } from './ApiKeysSection.strings'
import { type ApiKeyInfo } from '../types'

export function ApiKeysSection({
  keys,
  newKeyName,
  setNewKeyName,
  keyLoading,
  onCreate,
  revokingId,
  rotatingId,
  onRotate,
  onRevoke,
}: {
  keys: ApiKeyInfo[]
  newKeyName: string
  setNewKeyName: (v: string) => void
  keyLoading: boolean
  onCreate: () => void
  revokingId: number | null
  rotatingId: number | null
  onRotate: (id: number) => void
  onRevoke: (id: number) => void
}) {
  const lang = useLang()
  const s = apiKeysSectionStrings(lang)
  const f = fmt(lang)

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="key" size={16} className="text-accent" />
        <h2 className="card-title">{s.title}</h2>
        {keys.length > 0 && <span className="badge badge-accent">{f.num(keys.length)}</span>}
      </div>

      {/* Create new key */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <input
          className="input flex-1"
          value={newKeyName}
          onChange={(e) => setNewKeyName(e.target.value)}
          placeholder={s.namePlaceholder}
          onKeyDown={(e) => e.key === 'Enter' && onCreate()}
        />
        <button
          onClick={onCreate}
          disabled={keyLoading}
          className="btn btn-primary"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
        >
          {keyLoading ? (
            <span style={{ width: 14, height: 14, border: '2px solid #fff', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.6s linear infinite' }} />
          ) : (
            <Icon name="plus" size={14} />
          )}
          {s.create}
        </button>
      </div>

      {/* Key list */}
      {keys.length === 0 ? (
        <EmptyState icon="key" title={s.emptyTitle} description={s.emptyDesc} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {keys.map((k) => (
            <div key={k.id} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '12px 16px', borderRadius: 10,
              border: '1px solid var(--border)',
              opacity: k.active ? 1 : 0.6,
            }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>{k.name}</span>
                  {k.active ? (
                    <span className="badge badge-positive" style={{ fontSize: 10 }}>{s.active}</span>
                  ) : (
                    <span className="badge badge-danger" style={{ fontSize: 10 }}>{s.inactive}</span>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-muted)' }}>
                  <code style={{ direction: 'ltr' }}>{k.prefix}{'•'.repeat(20)}</code>
                  {k.created_at && <span>{f.date(k.created_at)}</span>}
                </div>
              </div>
              {k.active && (
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    onClick={() => onRotate(k.id)}
                    disabled={rotatingId === k.id}
                    className="btn btn-ghost btn-sm"
                    title={s.rotateTitle}
                  >
                    {rotatingId === k.id ? (
                      <span style={{ width: 12, height: 12, border: '2px solid var(--text-muted)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.6s linear infinite', display: 'inline-block' }} />
                    ) : (
                      <Icon name="refresh" size={13} />
                    )}
                  </button>
                  <button
                    onClick={() => onRevoke(k.id)}
                    disabled={revokingId === k.id}
                    className="btn btn-ghost btn-sm text-danger"
                    title={s.revokeTitle}
                  >
                    {revokingId === k.id ? (
                      <span style={{ width: 12, height: 12, border: '2px solid var(--danger)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.6s linear infinite', display: 'inline-block' }} />
                    ) : (
                      <Icon name="trash" size={13} />
                    )}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
