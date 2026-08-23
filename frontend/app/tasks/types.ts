import type { IconName } from '@/components/ui/Icon'
import { toFaDigits } from '@/lib/format'

/* ═══════════════════════════════════════════════════════════════════════════
   Shared types, constants, and formatters for the scheduled-tasks page.
   Split out of page.tsx to keep every file under the project's 500-line cap.
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

export const DELIVERY_CHANNELS: Record<string, { label: string; icon: IconName }> = {
  dashboard: { label: 'داشبورد', icon: 'dashboard' },
  email: { label: 'ایمیل', icon: 'mail' },
  telegram: { label: 'تلگرام', icon: 'chat' },
}

export const CRON_PRESETS = [
  { label: 'هر روز ساعت ۹ صبح', value: '0 9 * * *' },
  { label: 'هر روز ساعت ۱۲ شب', value: '0 0 * * *' },
  { label: 'هر ساعت', value: '0 * * * *' },
  { label: 'هر ۶ ساعت', value: '0 */6 * * *' },
  { label: 'هر هفته (دوشنبه)', value: '0 9 * * 1' },
  { label: 'هر ماه اول', value: '0 9 1 * *' },
]

export const STATUS_MAP: Record<string, { label: string; color: string }> = {
  success: { label: 'موفق', color: 'badge-positive' },
  failed: { label: 'ناموفق', color: 'badge-danger' },
  running: { label: 'در حال اجرا', color: 'badge-warning' },
}

export function describeCron(expr: string): string {
  if (!expr) return '—'
  const presets = CRON_PRESETS.find((p) => p.value === expr)
  if (presets) return presets.label
  const parts = expr.split(' ')
  if (parts.length !== 5) return expr
  const [min, hour, dom, mon, dow] = parts
  if (dom === '*' && mon === '*' && dow === '*') {
    if (hour !== '*' && min !== '*') return `هر روز ساعت ${hour}:${min.padStart(2, '0')}`
    if (hour !== '*') return `هر ساعت`
    return `هر ${min} دقیقه`
  }
  if (dow !== '*') {
    const days: Record<string, string> = {
      '0': 'یکشنبه', '1': 'دوشنبه', '2': 'سه‌شنبه', '3': 'چهارشنبه',
      '4': 'پنجشنبه', '5': 'جمعه', '6': 'شنبه',
    }
    const day = days[dow] || dow
    if (hour !== '*') return `هر ${day} ساعت ${hour}:${min.padStart(2, '0')}`
    return `هر ${day}`
  }
  return expr
}

export function formatDateTime(s: string | null): string {
  if (!s) return '—'
  return toFaDigits(
    new Date(s).toLocaleString('fa-IR', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    }),
  )
}
