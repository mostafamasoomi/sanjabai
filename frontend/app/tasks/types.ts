import type { IconName } from '@/components/ui/Icon'
import type { Lang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { tasksTypesStrings } from './types.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   Shared types, constants, and formatters for the scheduled-tasks page.
   Split out of page.tsx to keep every file under the project's 500-line cap.

   The constants/helpers below are plain functions, not components, so they
   take `lang` as an explicit parameter rather than calling `useLang()` --
   see the i18n spec ("a non-component helper takes lang as a parameter
   instead").
   ═══════════════════════════════════════════════════════════════════════════ */

export type Task = {
  id: number
  title: string
  description: string
  prompt: string
  model: string
  cron_expression: string
  is_active: boolean
  last_run_at: string | null
  next_run_at: string | null
  run_count: number
  last_result: string | null
  delivery_channel: string
  created_at: string
}

export type Execution = {
  id: number
  status: string
  result: string
  tokens_used: number
  // Absent on a backend that hasn't shipped cost reporting yet -- render
  // as "unknown", never as a bare `undefined` next to a currency label.
  cost_toman?: number
  error: string | null
  started_at: string
  completed_at: string | null
}

export type TaskForm = {
  title: string
  description: string
  prompt: string
  model: string
  cron_expression: string
  delivery_channel: string
}

export function deliveryChannels(lang: Lang): Record<string, { label: string; icon: IconName }> {
  const l = tasksTypesStrings(lang).deliveryChannels
  return {
    dashboard: { label: l.dashboard, icon: 'dashboard' },
    email: { label: l.email, icon: 'mail' },
    telegram: { label: l.telegram, icon: 'chat' },
  }
}

export function cronPresets(lang: Lang): { label: string; value: string }[] {
  return tasksTypesStrings(lang).cronPresets
}

export function statusMap(lang: Lang): Record<string, { label: string; color: string }> {
  const l = tasksTypesStrings(lang).statusMap
  return {
    success: { label: l.success, color: 'badge-positive' },
    failed: { label: l.failed, color: 'badge-danger' },
    running: { label: l.running, color: 'badge-warning' },
  }
}

export function describeCron(expr: string, lang: Lang): string {
  if (!expr) return '—'
  const s = tasksTypesStrings(lang)
  const presets = cronPresets(lang).find((p) => p.value === expr)
  if (presets) return presets.label
  const parts = expr.split(' ')
  if (parts.length !== 5) return expr
  const [min, hour, dom, mon, dow] = parts
  if (dom === '*' && mon === '*' && dow === '*') {
    if (hour !== '*' && min !== '*') return s.everyDayAt(`${hour}:${min.padStart(2, '0')}`)
    if (hour !== '*') return s.everyHour
    return s.everyNMinutes(min)
  }
  if (dow !== '*') {
    const day = s.weekdays[dow] || dow
    if (hour !== '*') return s.everyWeekdayAt(day, `${hour}:${min.padStart(2, '0')}`)
    return s.everyWeekday(day)
  }
  return expr
}

export function formatDateTime(iso: string | null, lang: Lang): string {
  if (!iso) return '—'
  const f = fmt(lang)
  return `${f.date(iso)} ${f.time(iso)}`
}
