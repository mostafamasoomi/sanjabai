import { describe, it, expect } from 'vitest'

import {
  applyToolStreamEvent, finalizeToolStreamState, EMPTY_TOOL_STREAM_STATE,
  type ToolStreamState,
} from '../../app/chat/hooks/useChatStream'
import {
  applyToolCallEvent, finalizeToolCalls, resolveToolChipLabel, toolCallChipStrings,
  type ToolCallEntry,
} from '../../app/chat/components/ToolCallChip.strings'
import {
  applyToolConfirmEvent, isConfirmableToolName, buildConfirmRequest, cronToReadable,
  toolConfirmCardStrings,
} from '../../app/chat/components/ToolConfirmCard.strings'

/**
 * Unit tests for the P-B6 tool-calling-loop UI event contract (design doc
 * §ب‑۲/§ب‑۶). The backend loop (chat_stream.py) is a parallel, not-yet-landed
 * packet -- these tests pin the CLIENT side of the SSE event shape:
 *
 *   {"type":"tool_call",    "name":"create_task", "status":"running", "label_fa":"…"}
 *   {"type":"tool_result",  "name":"create_task", "ok":true,          "label_fa":"…"}
 *   {"type":"tool_confirm", "name":"create_task", "preview":{...},    "label_fa":"…"}
 *
 * All pure (no React render needed -- these are the reducers/helpers
 * useChatStream.ts and the components call, not the components themselves).
 */

describe('applyToolStreamEvent -- additive dispatch (proof it cannot break today\'s traffic)', () => {
  it('an unknown type is ignored: same state reference back, no throw', () => {
    const state: ToolStreamState = { calls: [{ name: 'create_task', status: 'running' }], confirm: null }
    expect(() => applyToolStreamEvent(state, { type: 'billing', cost: 10 })).not.toThrow()
    expect(applyToolStreamEvent(state, { type: 'billing', cost: 10 })).toBe(state)
    expect(applyToolStreamEvent(state, { type: 'smart_info', model: 'x' })).toBe(state)
    expect(applyToolStreamEvent(state, { type: 'some_future_type_nobody_wrote_yet' })).toBe(state)
  })

  it('does not throw on malformed/non-object input (defends the JSON.parse boundary upstream)', () => {
    const state = EMPTY_TOOL_STREAM_STATE
    expect(() => applyToolStreamEvent(state, null)).not.toThrow()
    expect(() => applyToolStreamEvent(state, undefined)).not.toThrow()
    expect(() => applyToolStreamEvent(state, 'not an object')).not.toThrow()
    expect(() => applyToolStreamEvent(state, 42)).not.toThrow()
    expect(() => applyToolStreamEvent(state, [1, 2, 3])).not.toThrow()
    expect(() => applyToolStreamEvent(state, {})).not.toThrow()
    expect(() => applyToolStreamEvent(state, { type: 'tool_call' })).not.toThrow() // missing name
    expect(() => applyToolStreamEvent(state, { type: 'tool_confirm', preview: 'not-an-object' })).not.toThrow()
    expect(applyToolStreamEvent(state, null)).toBe(state)
    expect(applyToolStreamEvent(state, 'garbage')).toBe(state)
  })

  it('tool_call parses into a running call entry', () => {
    const next = applyToolStreamEvent(EMPTY_TOOL_STREAM_STATE, { type: 'tool_call', name: 'create_task', status: 'running', label_fa: 'در حال ساخت وظیفه…' })
    expect(next.calls).toEqual([{ name: 'create_task', status: 'running' }])
    expect(next.confirm).toBeNull()
  })

  it('tool_result with ok:true turns the matching running call into ok (not left running)', () => {
    const afterCall = applyToolStreamEvent(EMPTY_TOOL_STREAM_STATE, { type: 'tool_call', name: 'create_task', status: 'running' })
    const afterResult = applyToolStreamEvent(afterCall, { type: 'tool_result', name: 'create_task', ok: true, label_fa: 'وظیفه ساخته شد' })
    expect(afterResult.calls).toEqual([{ name: 'create_task', status: 'ok' }])
  })

  it('tool_result with ok:false renders as failed, never success', () => {
    const afterCall = applyToolStreamEvent(EMPTY_TOOL_STREAM_STATE, { type: 'tool_call', name: 'create_task', status: 'running' })
    const afterResult = applyToolStreamEvent(afterCall, { type: 'tool_result', name: 'create_task', ok: false })
    expect(afterResult.calls).toEqual([{ name: 'create_task', status: 'fail' }])
    expect(afterResult.calls[0].status).not.toBe('ok')
  })

  it('tool_result with a missing/non-boolean ok also renders as failed (ambiguous is never success)', () => {
    const afterCall = applyToolStreamEvent(EMPTY_TOOL_STREAM_STATE, { type: 'tool_call', name: 'create_task', status: 'running' })
    expect(applyToolStreamEvent(afterCall, { type: 'tool_result', name: 'create_task' }).calls[0].status).toBe('fail')
    expect(applyToolStreamEvent(afterCall, { type: 'tool_result', name: 'create_task', ok: 'true' }).calls[0].status).toBe('fail')
    expect(applyToolStreamEvent(afterCall, { type: 'tool_result', name: 'create_task', ok: 1 }).calls[0].status).toBe('fail')
  })

  it('tool_confirm parses into the confirm slot with a structured preview', () => {
    const next = applyToolStreamEvent(EMPTY_TOOL_STREAM_STATE, {
      type: 'tool_confirm', name: 'create_task',
      preview: { title: 'یادآوری روزانه', cron_expression: '0 9 * * *' },
      label_fa: 'می‌خواهید این وظیفه ساخته شود؟',
    })
    expect(next.confirm).toEqual({ name: 'create_task', preview: { title: 'یادآوری روزانه', cron_expression: '0 9 * * *' } })
    expect(next.calls).toEqual([]) // did not also add a call entry
  })
})

describe('finalizeToolStreamState -- the disconnect-mid-loop case (§ب‑۲)', () => {
  it('a tool_call never followed by tool_result ends up terminal (interrupted), not stuck running', () => {
    const afterCall = applyToolStreamEvent(EMPTY_TOOL_STREAM_STATE, { type: 'tool_call', name: 'create_task', status: 'running' })
    const finalState = finalizeToolStreamState(afterCall)
    expect(finalState.calls).toEqual([{ name: 'create_task', status: 'interrupted' }])
    expect(finalState.calls[0].status).not.toBe('running')
  })

  it('a call that already resolved is left alone by finalize (no reference change)', () => {
    const afterCall = applyToolStreamEvent(EMPTY_TOOL_STREAM_STATE, { type: 'tool_call', name: 'create_task', status: 'running' })
    const afterResult = applyToolStreamEvent(afterCall, { type: 'tool_result', name: 'create_task', ok: true })
    expect(finalizeToolStreamState(afterResult)).toBe(afterResult)
  })
})

describe('resolveToolChipLabel -- fixed client-side map, never the raw name or server label_fa', () => {
  it('known tool names get their specific Persian label', () => {
    expect(resolveToolChipLabel('create_task', 'running', 'fa')).toBe('در حال ساخت وظیفه…')
    expect(resolveToolChipLabel('create_task', 'ok', 'fa')).toBe('وظیفه ساخته شد')
    expect(resolveToolChipLabel('create_assistant', 'fail', 'fa')).toBe(toolCallChipStrings('fa').toolLabels.create_assistant.fail)
  })

  it('an unrecognised tool name renders the generic chip, never the raw name', () => {
    const evilNames = ['evil_tool_name_xyz', 'DROP TABLE users', '<script>alert(1)</script>', 'litellm_internal_route_9router']
    for (const name of evilNames) {
      const running = resolveToolChipLabel(name, 'running', 'fa')
      const ok = resolveToolChipLabel(name, 'ok', 'fa')
      const fail = resolveToolChipLabel(name, 'fail', 'fa')
      expect(running).toBe(toolCallChipStrings('fa').generic.running)
      expect(ok).toBe(toolCallChipStrings('fa').generic.ok)
      expect(fail).toBe(toolCallChipStrings('fa').generic.fail)
      // The direct assertion the packet asks for: the raw name never leaks
      // into rendered output, in any status, in any language.
      for (const label of [running, ok, fail, resolveToolChipLabel(name, 'running', 'en')]) {
        expect(label).not.toContain(name)
      }
    }
  })

  it('interrupted status always renders the generic "connection lost" text, even for a known tool', () => {
    expect(resolveToolChipLabel('create_task', 'interrupted', 'fa')).toBe(toolCallChipStrings('fa').interrupted)
    expect(resolveToolChipLabel('unknown_tool', 'interrupted', 'fa')).toBe(toolCallChipStrings('fa').interrupted)
  })

  it('no known-tool label anywhere in the map contains a raw internal identifier as a substring leak', () => {
    // Sanity check on the map itself: every rendered string is authored
    // Persian/English prose, not string-built from the tool name.
    const fa = toolCallChipStrings('fa')
    for (const key of Object.keys(fa.toolLabels) as (keyof typeof fa.toolLabels)[]) {
      const { running, ok, fail } = fa.toolLabels[key]
      for (const label of [running, ok, fail]) {
        expect(label).not.toContain(key)
      }
    }
  })
})

describe('applyToolCallEvent / finalizeToolCalls -- lower-level reducer used by applyToolStreamEvent', () => {
  it('a duplicate/unmatched tool_result is still recorded, not silently dropped', () => {
    const calls: ToolCallEntry[] = []
    const withResult = applyToolCallEvent(calls, { type: 'tool_result', name: 'create_task', ok: true })
    expect(withResult).toEqual([{ name: 'create_task', status: 'ok' }])
  })

  it('finalizeToolCalls only touches entries still running', () => {
    const mixed: ToolCallEntry[] = [
      { name: 'create_task', status: 'ok' },
      { name: 'create_assistant', status: 'running' },
      { name: 'list_models', status: 'fail' },
    ]
    expect(finalizeToolCalls(mixed)).toEqual([
      { name: 'create_task', status: 'ok' },
      { name: 'create_assistant', status: 'interrupted' },
      { name: 'list_models', status: 'fail' },
    ])
  })
})

describe('ToolConfirmCard reducer / request builder / cron translation', () => {
  it('applyToolConfirmEvent ignores every other event type (same reference back)', () => {
    expect(applyToolConfirmEvent(null, { type: 'tool_call', name: 'create_task' })).toBeNull()
    const existing = { name: 'create_task', preview: { title: 'x' } }
    expect(applyToolConfirmEvent(existing, { type: 'tool_result', name: 'create_task', ok: true })).toBe(existing)
    expect(applyToolConfirmEvent(existing, null)).toBe(existing)
  })

  it('only create_task/create_assistant are confirmable -- the closed action space', () => {
    expect(isConfirmableToolName('create_task')).toBe(true)
    expect(isConfirmableToolName('create_assistant')).toBe(true)
    expect(isConfirmableToolName('list_models')).toBe(false)
    expect(isConfirmableToolName('delete_everything')).toBe(false)
    expect(isConfirmableToolName('')).toBe(false)
  })

  it('buildConfirmRequest for create_task whitelists exactly the task fields, sentinel model', () => {
    const { url, body } = buildConfirmRequest('create_task', {
      title: 'یادآوری', prompt: 'به من یادآوری کن', cron_expression: '0 9 * * *', description: 'روزانه',
      // Attempted injection of fields the endpoint never accepts from here:
      is_active: true, model: 'sanjab/gpt-5', user_id: 999,
    })
    expect(url).toBe('/api/tasks')
    expect(body).toEqual({
      title: 'یادآوری', prompt: 'به من یادآوری کن', description: 'روزانه', cron_expression: '0 9 * * *', model: '',
    })
    expect(body).not.toHaveProperty('is_active')
    expect(body).not.toHaveProperty('user_id')
  })

  it('buildConfirmRequest for create_assistant always forces is_public:false and model_id:null regardless of preview', () => {
    const { url, body } = buildConfirmRequest('create_assistant', {
      name: 'دستیار من', system_prompt: 'تو یک دستیار مفیدی هستی', description: '',
      is_public: true, model_id: 42, // attempted override -- must be ignored
    })
    expect(url).toBe('/api/assistants')
    expect(body.is_public).toBe(false)
    expect(body.model_id).toBeNull()
    expect(body.name).toBe('دستیار من')
    expect(body.system_prompt).toBe('تو یک دستیار مفیدی هستی')
  })

  it('cronToReadable translates confident daily/weekly/interval patterns to Persian', () => {
    expect(cronToReadable('0 9 * * *', 'fa')).toBe('هر روز ساعت ۹ صبح')
    expect(cronToReadable('*/15 * * * *', 'fa')).toBe('هر ۱۵ دقیقه یک‌بار')
    expect(cronToReadable('0 */2 * * *', 'fa')).toBe('هر ۲ ساعت یک‌بار')
    expect(cronToReadable('0 * * * *', 'fa')).toBe('هر ساعت')
    expect(cronToReadable('0 14 * * *', 'fa')).toBe('هر روز ساعت ۲ بعدازظهر')
  })

  it('cronToReadable produces the same patterns in English with Latin digits -- no leftover Persian on a toggled-English screen', () => {
    expect(cronToReadable('0 9 * * *', 'en')).toBe('Every day at 9 AM')
    expect(cronToReadable('*/15 * * * *', 'en')).toBe('Every 15 minutes')
    expect(cronToReadable('0 */2 * * *', 'en')).toBe('Every 2 hours')
    expect(cronToReadable('0 * * * *', 'en')).toBe('Every hour')
    for (const lang of ['fa', 'en'] as const) {
      const out = cronToReadable('0 9 * * *', lang) ?? ''
      expect(/[؀-ۿ]/.test(out)).toBe(lang === 'fa')
    }
  })

  it('cronToReadable returns null (never a guess) for anything it is not confident about, so the raw expression is shown instead', () => {
    expect(cronToReadable('*/5 9-17 * * 1-5', 'fa')).toBeNull() // range/step combo
    expect(cronToReadable('0 9 * * mon', 'fa')).toBeNull()      // named weekday, not numeric
    expect(cronToReadable('0 9 * jan *', 'fa')).toBeNull()      // month restricted
    expect(cronToReadable('not a cron at all', 'fa')).toBeNull()
    expect(cronToReadable('', 'fa')).toBeNull()
    expect(cronToReadable('99 99 * * *', 'fa')).toBeNull()      // out-of-range hour/minute
  })

  it('the unsupported-tool card path never gets a submit target: buildConfirmRequest is only ever called for confirmable names in the component, guarded by isConfirmableToolName', () => {
    // Documents the contract the component relies on -- buildConfirmRequest
    // itself is typed to ConfirmableToolName, so calling it for an unknown
    // name is a compile-time error, not a runtime branch to test.
    expect(isConfirmableToolName('create_task') && isConfirmableToolName('create_assistant')).toBe(true)
  })

  it('bilingual strings stay in sync (dict() compile-time contract) and the FA confirm question never contains the raw tool name', () => {
    const fa = toolConfirmCardStrings('fa')
    const en = toolConfirmCardStrings('en')
    expect(fa.questionByTool.create_task).not.toContain('create_task')
    expect(en.questionByTool.create_task).not.toContain('create_task')
    expect(fa.confirm).toBeTruthy()
    expect(en.confirm).toBeTruthy()
  })
})

/* ── Senior wiring guard (2026-08-28) ──────────────────────────────────────
 *
 * The packet that built ToolCallChip and ToolConfirmCard could not mount
 * them: ChatMessageItem.tsx and chat/page.tsx are senior-owned. So for a
 * while both components existed, were fully unit-tested, and rendered for
 * nobody -- every assertion above passed and no user could see a chip.
 *
 * That is the failure this file could not otherwise catch, so the mount is
 * asserted directly against the source. Not elegant; the alternative is a
 * component whose tests are all green while it is unreachable, which this
 * repository has shipped before.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

describe('the tool UI is actually mounted', () => {
  const messageItem = readFileSync(
    join(__dirname, '../../app/chat/components/ChatMessageItem.tsx'), 'utf-8',
  )
  const chatPage = readFileSync(
    join(__dirname, '../../app/chat/page.tsx'), 'utf-8',
  )

  it('ChatMessageItem renders both tool components', () => {
    expect(messageItem).toContain('<ToolCallChip')
    expect(messageItem).toContain('<ToolConfirmCard')
  })

  it('ChatMessageItem accepts the toolEvents prop it needs to render them', () => {
    expect(messageItem).toMatch(/toolEvents\?:\s*ToolStreamState/)
  })

  it('the chat page passes tool events down per message', () => {
    expect(chatPage).toContain('toolEventsByMessageId[msg.id]')
  })
})
