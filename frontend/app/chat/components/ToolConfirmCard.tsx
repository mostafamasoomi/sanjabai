'use client'

import { useState } from 'react'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { Icon } from '@/components/ui/Icon'
import { Spinner } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { dirFor } from '@/lib/i18n'
import {
  toolConfirmCardStrings, isConfirmableToolName, buildConfirmRequest, cronToReadable,
} from './ToolConfirmCard.strings'

export type ToolConfirmCardProps = {
  /** Raw backend tool name -- checked against the closed allow-list in
   *  ToolConfirmCard.strings.ts before anything becomes actionable. */
  name: string
  preview: Record<string, unknown>
}

type SubmitState = 'idle' | 'submitting' | 'done' | 'error'

/**
 * Renders a `tool_confirm` event as data, per §ب‑۶: the SSE stream that
 * produced this has already closed by the time the user sees the button --
 * there is no pending server-side state to resume. Confirming just fires an
 * ordinary POST to the same endpoint the user could hit by hand from
 * /tasks or /assistants/new. Message data, so it must render identically
 * after a page reload once persisted -- no live-stream-only state here.
 */
export default function ToolConfirmCard({ name, preview }: ToolConfirmCardProps) {
  const lang = useLang()
  const s = toolConfirmCardStrings(lang)
  const { token } = useAuth()
  const [state, setState] = useState<SubmitState>('idle')

  const cardStyle: React.CSSProperties = {
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    padding: '14px 16px',
    margin: '8px 0',
    background: 'var(--bg-secondary, rgba(255,255,255,0.04))',
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    fontSize: '0.85rem',
  }

  if (!isConfirmableToolName(name)) {
    return (
      <div dir={dirFor(lang)} style={{ ...cardStyle, borderColor: 'var(--danger-dim)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--danger)', fontWeight: 600 }}>
          <Icon name="warning" size={15} />
          {s.unsupportedTitle}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>{s.unsupportedBody}</div>
      </div>
    )
  }

  const handleConfirm = async () => {
    if (!token || state === 'submitting') return
    setState('submitting')
    try {
      const { url, body } = buildConfirmRequest(name, preview)
      const res = await apiFetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      })
      setState(res.ok ? 'done' : 'error')
    } catch {
      setState('error')
    }
  }

  const cronExpr = name === 'create_task' && typeof preview.cron_expression === 'string' ? preview.cron_expression : null
  const cronReadable = cronExpr ? cronToReadable(cronExpr, lang) : null
  const title = typeof preview.title === 'string' ? preview.title : ''
  const prompt = typeof preview.prompt === 'string' ? preview.prompt : ''
  const description = typeof preview.description === 'string' ? preview.description : ''
  const assistantName = typeof preview.name === 'string' ? preview.name : ''
  const systemPrompt = typeof preview.system_prompt === 'string' ? preview.system_prompt : ''

  return (
    <div dir={dirFor(lang)} style={cardStyle}>
      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{s.questionByTool[name]}</div>

      <dl style={{ margin: 0, display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {name === 'create_task' && title && <Field label={s.fields.title} value={title} />}
        {name === 'create_task' && prompt && <Field label={s.fields.prompt} value={prompt} />}
        {name === 'create_task' && description && <Field label={s.fields.description} value={description} />}
        {name === 'create_task' && cronExpr && (
          <Field
            label={s.fields.schedule}
            value={cronReadable ?? cronExpr}
            secondary={cronReadable ? `${s.fields.rawCron}: ${cronExpr}` : undefined}
          />
        )}
        {name === 'create_assistant' && assistantName && <Field label={s.fields.name} value={assistantName} />}
        {name === 'create_assistant' && description && <Field label={s.fields.description} value={description} />}
        {name === 'create_assistant' && systemPrompt && <Field label={s.fields.systemPrompt} value={systemPrompt} />}
      </dl>

      {state === 'done' ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--success)' }}>
          <Icon name="check" size={14} />
          <span>{name === 'create_task' ? s.confirmedTask : s.confirmedAssistant}</span>
          <a href={name === 'create_task' ? '/tasks' : '/assistants'} style={{ color: 'var(--accent)' }}>
            {name === 'create_task' ? s.goToTasks : s.goToAssistants}
          </a>
        </div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={state === 'submitting' || !token}
            className="btn btn-primary btn-sm"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          >
            {state === 'submitting' && <Spinner size="sm" />}
            {state === 'submitting' ? s.confirming : s.confirm}
          </button>
          {state === 'error' && <span style={{ color: 'var(--danger)' }}>{s.failed}</span>}
        </div>
      )}
    </div>
  )
}

function Field({ label, value, secondary }: { label: string; value: string; secondary?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
      <dt style={{ color: 'var(--text-muted, var(--text-secondary))', fontSize: '0.7rem' }}>{label}</dt>
      <dd style={{ margin: 0, color: 'var(--text-primary)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
        {value}
        {secondary && (
          <span style={{ display: 'block', color: 'var(--text-muted, var(--text-secondary))', fontSize: '0.7rem', marginTop: '2px' }}>
            {secondary}
          </span>
        )}
      </dd>
    </div>
  )
}
