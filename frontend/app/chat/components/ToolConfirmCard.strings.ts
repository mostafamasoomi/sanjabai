import { dict, fmt } from '@/lib/i18n'
import { toFaDigits } from '@/lib/format'
import type { Lang } from '@/components/LanguageToggle'

/* ═══════════════════════════════════════════════════════════════════════════
   ToolConfirmCard -- labels, the tool_confirm reducer, cron→Persian, and the
   confirm-button request builder (P-B6, §ب‑۶).

   §ب‑۶'s key design point: the stream does NOT stay open waiting for the
   user. `tool_confirm` closes the stream immediately; there is no pending
   server-side state. This card is pure data (a tool name + a structured
   `preview`) and its confirm button is an ordinary `POST /api/tasks` or
   `/api/assistants` -- the exact same request a user could make by hand
   through the pages that have worked for months. Nothing here depends on
   the stream still being open.
   ═══════════════════════════════════════════════════════════════════════════ */

export type ToolConfirmEntry = {
  name: string
  /** Structured fields only (e.g. `{title, cron_expression}`) -- never a
   *  free-text/arguments blob. buildConfirmRequest whitelists which of
   *  these keys are actually sent per tool name. */
  preview: Record<string, unknown>
}

/** Pure reducer for the `tool_confirm` SSE line. Returns the SAME reference
 *  for any other event, so callers can skip a re-render. Never throws. */
export function applyToolConfirmEvent(current: ToolConfirmEntry | null, obj: any): ToolConfirmEntry | null {
  if (!obj || typeof obj !== 'object' || obj.type !== 'tool_confirm') return current
  const name = typeof obj.name === 'string' ? obj.name : ''
  const preview = obj.preview && typeof obj.preview === 'object' && !Array.isArray(obj.preview) ? obj.preview : {}
  return { name, preview }
}

/* ── the closed action space -- mirrors the backend's frozenset (§ب‑۵.۴):
   only these two tool names can ever become a confirm-and-submit action.
   Anything else renders the "unsupported" card and has NO submit button. ── */

export type ConfirmableToolName = 'create_task' | 'create_assistant'
const CONFIRMABLE_TOOL_NAMES: readonly ConfirmableToolName[] = ['create_task', 'create_assistant']

export function isConfirmableToolName(name: string): name is ConfirmableToolName {
  return (CONFIRMABLE_TOOL_NAMES as readonly string[]).includes(name)
}

/** Whitelisted POST target + body for the confirm button, built from the
 *  server's `preview` -- never the raw SSE event, and never any preview key
 *  outside this list. Truncated to the same bounds §ب‑۳ documents for the
 *  backend's own validation (defence in depth, not a substitute for it). */
export type ConfirmRequest = { url: string; body: Record<string, unknown> }

function str(v: unknown, max: number): string {
  return typeof v === 'string' ? v.slice(0, max) : ''
}

export function buildConfirmRequest(name: ConfirmableToolName, preview: Record<string, unknown>): ConfirmRequest {
  if (name === 'create_task') {
    return {
      url: '/api/tasks',
      body: {
        title: str(preview.title, 100),
        prompt: str(preview.prompt, 10000),
        description: str(preview.description, 500),
        cron_expression: str(preview.cron_expression, 100),
        // Sentinel: the model never picks a model, tasks.py resolves it.
        model: '',
      },
    }
  }
  return {
    url: '/api/assistants',
    body: {
      name: str(preview.name, 100),
      system_prompt: str(preview.system_prompt, 8000),
      description: str(preview.description, 500) || null,
      model_id: null,
      // 🚨 Always false -- the model never gets to publish data (§ب‑۵.۲).
      is_public: false,
    },
  }
}

/* ── cron → readable text, bilingual ─────────────────────────────────────
   Digits go through `fmt(lang).num` (never `faNum` directly -- this is a
   USER-FACING file, and the product's i18n coverage guard,
   tests/lib/productI18nCoverage.test.ts, enforces exactly that: faNum
   hardcodes Persian digits regardless of the active language). The
   surrounding weekday/time-of-day words are translated by hand below for
   the same reason -- an English-toggled user must not still get a Persian
   sentence just because the digits inside it were fixed. */

const WEEKDAY: Record<Lang, string[]> = {
  fa: ['یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه', 'شنبه'],
  en: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
}

function timeOfDay(hour: number, lang: Lang): string {
  if (lang === 'en') {
    if (hour === 0) return 'midnight'
    if (hour < 12) return 'AM'
    if (hour === 12) return 'noon'
    return 'PM'
  }
  if (hour === 0) return 'نیمه‌شب'
  if (hour < 12) return 'صبح'
  if (hour === 12) return 'ظهر'
  if (hour < 17) return 'بعدازظهر'
  if (hour < 21) return 'عصر'
  return 'شب'
}

function hourMinute(hour: number, minute: number, lang: Lang): string {
  const hour12 = hour % 12 === 0 ? 12 : hour % 12
  const h = fmt(lang).num(hour12)
  if (minute === 0) return h
  // Zero-padded, so it must not go through fmt().num (which drops the
  // leading zero as a formatted integer) -- toFaDigits only swaps digits.
  const mm = String(minute).padStart(2, '0')
  return `${h}:${lang === 'en' ? mm : toFaDigits(mm)}`
}

/**
 * Confident, whitelisted 5-field cron patterns only -- returns `null` (never
 * a guess) for anything else. §ب‑۶ is explicit: a wrong gloss on a schedule
 * the user then approves is worse than an untranslated one, so
 * ToolConfirmCard must fall back to the raw expression when this returns
 * null, not attempt a looser translation.
 */
export function cronToReadable(expr: string, lang: Lang): string | null {
  const parts = expr.trim().split(/\s+/)
  if (parts.length !== 5) return null
  const [min, hour, dom, month, dow] = parts
  if (month !== '*') return null

  const isNum = (v: string) => /^\d+$/.test(v)
  const n = fmt(lang).num

  const everyMin = min.match(/^\*\/(\d+)$/)
  if (everyMin && hour === '*' && dom === '*' && dow === '*') {
    const k = n(Number(everyMin[1]))
    return lang === 'en' ? `Every ${k} minutes` : `هر ${k} دقیقه یک‌بار`
  }

  if (isNum(min) && hour === '*' && dom === '*' && dow === '*') {
    if (Number(min) === 0) return lang === 'en' ? 'Every hour' : 'هر ساعت'
    const k = n(Number(min))
    return lang === 'en' ? `Every hour, at minute ${k}` : `هر ساعت، دقیقهٔ ${k}`
  }

  const everyHour = hour.match(/^\*\/(\d+)$/)
  if (isNum(min) && Number(min) === 0 && everyHour && dom === '*' && dow === '*') {
    const k = n(Number(everyHour[1]))
    return lang === 'en' ? `Every ${k} hours` : `هر ${k} ساعت یک‌بار`
  }

  if (isNum(min) && isNum(hour) && dom === '*' && dow === '*') {
    const h = Number(hour), m = Number(min)
    if (h > 23 || m > 59) return null
    const time = `${hourMinute(h, m, lang)} ${timeOfDay(h, lang)}`
    return lang === 'en' ? `Every day at ${time}` : `هر روز ساعت ${time}`
  }

  if (isNum(min) && isNum(hour) && dom === '*' && /^[0-6]$/.test(dow)) {
    const h = Number(hour), m = Number(min), d = Number(dow)
    if (h > 23 || m > 59) return null
    const time = `${hourMinute(h, m, lang)} ${timeOfDay(h, lang)}`
    return lang === 'en' ? `Every ${WEEKDAY.en[d]} at ${time}` : `هر ${WEEKDAY.fa[d]} ساعت ${time}`
  }

  if (isNum(min) && isNum(hour) && isNum(dom) && dow === '*') {
    const h = Number(hour), m = Number(min), d = Number(dom)
    if (h > 23 || m > 59 || d < 1 || d > 31) return null
    const time = `${hourMinute(h, m, lang)} ${timeOfDay(h, lang)}`
    const k = n(d)
    return lang === 'en' ? `On day ${k} of every month at ${time}` : `روز ${k} هر ماه ساعت ${time}`
  }

  return null
}

/* ── strings ──────────────────────────────────────────────────────────── */

const FA = {
  questionByTool: {
    create_task: 'می‌خواهید این وظیفه ساخته شود؟',
    create_assistant: 'می‌خواهید این دستیار ساخته شود؟',
  },
  unsupportedTitle: 'این درخواست پشتیبانی نمی‌شود',
  unsupportedBody: 'دستیار هوش مصنوعی خواست عملیاتی انجام دهد که این نسخه از برنامه آن را نمی‌شناسد. برای امنیت شما، این عملیات اجرا نمی‌شود.',
  fields: {
    title: 'عنوان',
    description: 'توضیح',
    prompt: 'دستور وظیفه',
    schedule: 'زمان‌بندی',
    rawCron: 'عبارت خام',
    name: 'نام',
    systemPrompt: 'دستور سیستمی',
  },
  confirm: 'تأیید و ساخت',
  confirming: 'در حال ساخت…',
  confirmedTask: 'وظیفه با موفقیت ساخته شد.',
  confirmedAssistant: 'دستیار با موفقیت ساخته شد.',
  failed: 'ساخت انجام نشد. دوباره تلاش کنید یا خودتان از صفحهٔ مربوطه بسازید.',
  goToTasks: 'رفتن به وظیفه‌ها',
  goToAssistants: 'رفتن به دستیارها',
}

const EN: typeof FA = {
  questionByTool: {
    create_task: 'Create this task?',
    create_assistant: 'Create this assistant?',
  },
  unsupportedTitle: 'This request is not supported',
  unsupportedBody: 'The assistant tried to perform an action this version of the app does not recognize. For your safety, it was not run.',
  fields: {
    title: 'Title',
    description: 'Description',
    prompt: 'Task prompt',
    schedule: 'Schedule',
    rawCron: 'Raw expression',
    name: 'Name',
    systemPrompt: 'System prompt',
  },
  confirm: 'Confirm and create',
  confirming: 'Creating…',
  confirmedTask: 'Task created successfully.',
  confirmedAssistant: 'Assistant created successfully.',
  failed: 'Creation failed. Try again, or create it yourself from the relevant page.',
  goToTasks: 'Go to tasks',
  goToAssistants: 'Go to assistants',
}

export const toolConfirmCardStrings = dict(FA, EN)
