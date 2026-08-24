import { useState } from 'react'
import { toast, Tabs } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { CODE_EXAMPLES } from '../constants'

function copyText(text: string) {
  navigator.clipboard.writeText(text)
  toast('کپی شد', 'success')
}

export function CodeExamplesSection() {
  const [activeTab, setActiveTab] = useState('python')
  const example = CODE_EXAMPLES[activeTab as keyof typeof CODE_EXAMPLES]

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Icon name="code" size={16} className="text-accent" />
        <h2 className="card-title">نمونه کد</h2>
      </div>

      <Tabs
        tabs={[
          { key: 'python', label: 'Python' },
          { key: 'curl', label: 'cURL' },
          { key: 'javascript', label: 'JavaScript' },
        ]}
        active={activeTab}
        onChange={setActiveTab}
      />

      <div style={{ marginTop: 16 }}>
        {/* Install command */}
        {example.install && (
          <div style={{ marginBottom: 12 }}>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, display: 'block' }}>نصب وابستگی:</span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <code style={{
                flex: 1, padding: '8px 14px', borderRadius: 8,
                background: 'var(--bg-surface, var(--bg-elev))',
                fontSize: 13, direction: 'ltr', fontFamily: 'var(--font-mono)',
                color: 'var(--text-primary)',
              }}>
                $ {example.install}
              </code>
              <button
                onClick={() => copyText(example.install!)}
                className="btn btn-ghost btn-sm shrink-0"
              >
                <Icon name="copy" size={13} />
              </button>
            </div>
          </div>
        )}

        {/* Code block */}
        <div className="relative">
          <pre style={{
            padding: '16px 18px', borderRadius: 10,
            background: 'var(--bg-surface, var(--bg-elev))',
            border: '1px solid var(--border)',
            fontSize: 13, direction: 'ltr', textAlign: 'left',
            fontFamily: 'var(--font-mono)', lineHeight: 1.7,
            overflow: 'auto', color: 'var(--text-primary)',
            maxHeight: 400,
          }}>
            <code>{example.code}</code>
          </pre>
          <button
            onClick={() => copyText(example.code)}
            className="btn btn-ghost btn-sm"
            style={{ position: 'absolute', top: 8, left: 8, display: 'inline-flex', alignItems: 'center', gap: 4 }}
          >
            <Icon name="copy" size={12} />
            کپی
          </button>
        </div>
      </div>
    </div>
  )
}
