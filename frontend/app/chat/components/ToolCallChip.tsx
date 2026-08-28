import { Icon } from '@/components/ui/Icon'
import { Spinner } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { dirFor } from '@/lib/i18n'
import { resolveToolChipLabel, type ToolChipStatus } from './ToolCallChip.strings'

export type ToolCallChipProps = {
  /** Raw backend tool name (e.g. `create_task`). Used ONLY to look this
   *  chip's label up in resolveToolChipLabel's fixed map -- never rendered
   *  directly, and never the server-supplied `label_fa`. See
   *  ToolCallChip.strings.ts for the enforcement point. */
  name: string
  status: ToolChipStatus
}

const STATUS_COLOR: Record<ToolChipStatus, string> = {
  running: 'var(--text-secondary)',
  ok: 'var(--success)',
  fail: 'var(--danger)',
  interrupted: 'var(--text-muted, var(--text-secondary))',
}

const STATUS_BG: Record<ToolChipStatus, string> = {
  running: 'var(--bg-secondary, rgba(255,255,255,0.05))',
  ok: 'var(--success-dim)',
  fail: 'var(--danger-dim)',
  interrupted: 'var(--bg-secondary, rgba(255,255,255,0.05))',
}

/** One SSE `tool_call`/`tool_result` turned into a small Persian status
 *  chip -- e.g. «در حال ساخت وظیفه…» that later becomes «وظیفه ساخته شد».
 *  Presentational only; all state lives in useChatStream's
 *  toolEventsByMessageId (see that file's ToolStreamState comment). */
export default function ToolCallChip({ name, status }: ToolCallChipProps) {
  const lang = useLang()
  const label = resolveToolChipLabel(name, status, lang)
  return (
    <span
      dir={dirFor(lang)}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        padding: '4px 10px',
        margin: '2px 0',
        borderRadius: 'var(--radius-full, 999px)',
        border: '1px solid var(--border)',
        background: STATUS_BG[status],
        color: STATUS_COLOR[status],
        fontSize: '0.75rem',
        fontWeight: 500,
      }}
    >
      {status === 'running' && <Spinner size="sm" />}
      {status === 'ok' && <Icon name="check" size={13} />}
      {status === 'fail' && <Icon name="close" size={13} />}
      {status === 'interrupted' && <Icon name="warning" size={13} />}
      {label}
    </span>
  )
}
