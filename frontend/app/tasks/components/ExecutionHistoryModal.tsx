'use client'

import { Modal } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { type Execution, statusMap, formatDateTime } from '../types'
import { executionHistoryModalStrings } from './ExecutionHistoryModal.strings'

export default function ExecutionHistoryModal({
  open,
  onClose,
  taskTitle,
  executions,
}: {
  open: boolean
  onClose: () => void
  taskTitle: string
  executions: Execution[]
}) {
  const lang = useLang()
  const s = executionHistoryModalStrings(lang)
  const f = fmt(lang)
  const status = statusMap(lang)

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={s.modalTitle(taskTitle)}
    >
      {executions.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-muted)' }}>
          <Icon name="history" size={32} style={{ marginBottom: 8 }} />
          <p>{s.empty}</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {executions.map((ex) => {
            const st = status[ex.status] || { label: ex.status, color: 'badge-accent' }
            return (
              <div key={ex.id} style={{
                padding: '12px 14px', borderRadius: 8,
                border: '1px solid var(--border)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span className={`badge ${st.color}`} style={{ fontSize: 11 }}>{st.label}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    {formatDateTime(ex.started_at, lang)}
                  </span>
                </div>
                {ex.error && (
                  <p style={{ fontSize: 12, color: 'var(--danger)', margin: '4px 0', direction: 'ltr', fontFamily: 'var(--font-mono)' }}>
                    {ex.error}
                  </p>
                )}
                {ex.result && (
                  <div style={{
                    fontSize: 12, color: 'var(--text-secondary)', direction: 'ltr', textAlign: 'left',
                    fontFamily: 'var(--font-mono)', maxHeight: 60, overflow: 'hidden',
                    lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                  }}>
                    {ex.result.slice(0, 200)}{ex.result.length > 200 ? '...' : ''}
                  </div>
                )}
                <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
                  {ex.tokens_used > 0 && (
                    <span>{s.tokens(f.num(ex.tokens_used))}</span>
                  )}
                  {(ex.cost_toman ?? 0) > 0 && (
                    <span>{f.price(ex.cost_toman)}</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Modal>
  )
}
