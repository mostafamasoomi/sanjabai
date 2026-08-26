'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { endpoints } from '../constants'
import { endpointDocsSectionStrings } from './EndpointDocsSection.strings'

export function EndpointDocsSection() {
  const lang = useLang()
  const s = endpointDocsSectionStrings(lang)

  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="external" size={16} className="text-accent" />
        <h2 className="card-title">{s.title}</h2>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {endpoints(lang).map((ep) => (
          <div key={ep.path} style={{
            padding: '16px 18px', borderRadius: 10,
            border: '1px solid var(--border)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <span style={{
                padding: '3px 10px', borderRadius: 6, fontSize: 11, fontWeight: 700,
                fontFamily: 'var(--font-mono)',
                background: ep.method === 'POST' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(59, 130, 246, 0.1)',
                color: ep.method === 'POST' ? 'var(--positive)' : 'var(--info)',
              }}>
                {ep.method}
              </span>
              <code style={{ fontSize: 14, fontWeight: 600, direction: 'ltr', fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                {ep.path}
              </code>
            </div>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '0 0 10px' }}>{ep.desc}</p>

            {ep.body && (
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{s.sampleRequest}</div>
                <pre style={{
                  padding: '10px 14px', borderRadius: 8,
                  background: 'var(--bg-surface, var(--bg-elev))',
                  fontSize: 12, direction: 'ltr', textAlign: 'left',
                  fontFamily: 'var(--font-mono)', lineHeight: 1.6, overflow: 'auto',
                  color: 'var(--text-secondary)',
                }}>
                  <code>{ep.body}</code>
                </pre>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
