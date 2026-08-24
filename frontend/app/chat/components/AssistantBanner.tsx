import { Icon, type IconName } from '@/components/ui/Icon'
import type { Assistant } from '../chatTypes'

type AssistantBannerProps = {
  activeAssistant: Assistant | null
  loadingAssistant: boolean
}

export default function AssistantBanner({ activeAssistant, loadingAssistant }: AssistantBannerProps) {
  if (!activeAssistant && !loadingAssistant) return null
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        padding: '0.75rem 1rem',
        background: 'var(--bg-surface)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      {loadingAssistant ? (
        <div className="skeleton" style={{ width: '100%', height: '1.5rem', borderRadius: 'var(--radius-sm)' }} />
      ) : activeAssistant ? (
        <>
          <div
            style={{
              width: '2rem',
              height: '2rem',
              borderRadius: 'var(--radius-md)',
              background: 'var(--accent)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <Icon name={(activeAssistant.icon as IconName) || 'sparkles'} size={16} className="text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              {activeAssistant.name}
            </div>
            {activeAssistant.description && (
              <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {activeAssistant.description}
              </div>
            )}
          </div>
          <a
            href={`/assistants/${activeAssistant.id}`}
            className="btn btn-ghost btn-sm"
            style={{ fontSize: '0.6875rem', flexShrink: 0 }}
          >
            <Icon name="settings" size={12} />
            تنظیمات
          </a>
        </>
      ) : null}
    </div>
  )
}
