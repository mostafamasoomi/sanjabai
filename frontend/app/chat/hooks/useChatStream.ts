import { useRef, useCallback, useEffect, type MutableRefObject } from 'react'
import { apiFetch } from '@/lib/apiFetch'
import { toast } from '@/components/ui'
import { type ModelCatalogItem } from '@/types/catalog'
import { StreamAccumulator } from '../useStreamAccumulator'
import type { Message, UsageStats, Assistant } from '../chatTypes'
import { generateId, hasSearchIntent } from '../chatHelpers'

type SearchHint = { userMsgId: string; content: string } | null

type UseChatStreamParams = {
  model: ModelCatalogItem | null
  models: ModelCatalogItem[]
  setModel: (m: ModelCatalogItem) => void
  token: string | null
  smartMode: boolean
  webSearch: boolean
  setWebSearch: (v: boolean) => void
  attachedFile: File | null
  setAttachedFile: (f: File | null) => void
  activeAssistant: Assistant | null
  messages: Message[]
  setMessages: (updater: Message[] | ((prev: Message[]) => Message[])) => void
  setInput: (v: string) => void
  messagesRef: MutableRefObject<Message[]>
  activeConversationIdRef: MutableRefObject<string | null>
  createConversation: (firstUserMsg: string) => Promise<string | null>
  saveMessages: (convId: string, msgs: Message[]) => Promise<void>
  setSmartModel: (v: string | null) => void
  setShowPresets: (v: boolean) => void
  setWalletBalance: (v: number) => void
  abortRef: MutableRefObject<AbortController | null>
  // Owned by the page (ChatErrorBanner/composer footer read these directly,
  // and useConversations' startNewChat/loadConversation also reset them) --
  // this hook only ever writes them, so no circular hook-to-hook dependency.
  setStreaming: (v: boolean) => void
  setError: (v: string) => void
  setUsageStats: (updater: UsageStats | ((prev: UsageStats) => UsageStats)) => void
  setTokensPerSec: (v: number) => void
  searchHintFor: SearchHint
  setSearchHintFor: (v: SearchHint) => void
}

// The SSE-streaming core of the chat page. Kept as one hook (rather than
// split further) because sendMessage/retry/cancel/handleContinue all share
// the same abortRef/streaming/searchHintFor state and the reader loop's
// closures (processLine, streamAccumulator) must not be pulled apart from
// the setStreaming/setMessages calls that bracket them -- see session 11's
// note on why this file was left alone before.
export function useChatStream(params: UseChatStreamParams) {
  const {
    model, models, setModel, token, smartMode, webSearch, setWebSearch,
    attachedFile, setAttachedFile, activeAssistant, messages, setMessages, setInput, messagesRef,
    activeConversationIdRef, createConversation, saveMessages, setSmartModel, setShowPresets,
    setWalletBalance, abortRef, setStreaming, setError, setUsageStats, setTokensPerSec,
    searchHintFor, setSearchHintFor,
  } = params

  const streamStartTimeRef = useRef<number>(0)

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setStreaming(false)
  }, [abortRef])

  const sendMessageRef = useRef<((content: string, existingMsgs?: Message[]) => Promise<void>) | null>(null)

  const sendMessage = useCallback(async (content: string, existingMsgs?: Message[], forceWebSearch?: boolean) => {
    let currentModel = model;
    if (!currentModel && models.length > 0) {
        currentModel = models[0];
        setModel(models[0]); // Ensure model state is updated
    }
    if (!currentModel) {
      toast('لطفاً یک مدل را انتخاب کنید.', 'error');
      return;
    }
    const effectiveWebSearch = forceWebSearch ?? webSearch
    if (forceWebSearch && !webSearch) setWebSearch(true)
    const msgs = existingMsgs || messages
    const userMsg: Message = { id: generateId(), role: 'user', content }
    // Offer the re-send-with-search hint only for organic sends (not the
    // forced resend itself) when search is off but the message reads like
    // a search request.
    setSearchHintFor(!forceWebSearch && !webSearch && hasSearchIntent(content) ? { userMsgId: userMsg.id, content } : null)
    const updated = [...msgs, userMsg]
    setMessages(updated)
    setInput('')
    setShowPresets(false)
    setStreaming(true)
    setError('')
    streamStartTimeRef.current = Date.now()
    setTokensPerSec(0)

    const controller = new AbortController()
    abortRef.current = controller

    // If no active conversation, create one on first user message
    let convId = activeConversationIdRef.current
    if (!convId) {
      convId = await createConversation(content)
    }

    // Outside try so the AbortError catch branch can flush pending tokens.
    let streamAccumulator: StreamAccumulator | null = null

    try {
      const chatUrl = (smartMode && !attachedFile) ? '/api/v1/smart-chat' : '/api/v1/chat/completions'
      let res: Response
      if (attachedFile) {
        const fd = new FormData()
        fd.append('file', attachedFile)
        fd.append('model', currentModel!.providerModelId || currentModel!.id)
        fd.append('messages', JSON.stringify(updated.map(m => ({ role: m.role, content: m.content }))))
        fd.append('stream', 'true')
        const fh: Record<string, string> = {}
        if (token) fh['Authorization'] = `Bearer ${token}`
        res = await apiFetch('/api/v1/chat/with-file', { method: 'POST', headers: fh, body: fd, signal: controller.signal })
        setAttachedFile(null)
      } else {
        res = await apiFetch(chatUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            ...(smartMode ? { 'X-Smart-Model': currentModel!.providerModelId || currentModel!.id } : {}),
          },
          body: JSON.stringify({
            model: currentModel!.providerModelId || currentModel!.id,
            messages: updated.map(m => ({ role: m.role, content: m.content })),
            stream: true,
            ...(effectiveWebSearch ? { web_search: true } : {}),
            ...(activeAssistant ? { assistant_id: activeAssistant.id } : {}),
          }),
          signal: controller.signal,
        })
      }

      if (!res.ok) {
        let errorBody: { error?: { code?: string; message?: string }; code?: string; detail?: string } | null = null
        try { errorBody = await res.json() } catch {}
        const code = errorBody?.error?.code || errorBody?.code || ''
        // Only a real balance failure gets the "your credit has run out" card.
        // This used to fire on ANY 429, so a user with ~10,000,000 toman who
        // merely hit the five-free-messages-per-model window was told their
        // credit was finished and sent to the top-up page -- false, and it
        // pushed people to pay for something they had already paid for.
        // Every other error now shows the server's own Persian message, which
        // is already specific (the free-tier one names the model and counts
        // down to the reset).
        if (code === 'balance') {
          throw new Error('INSUFFICIENT_BALANCE')
        }
        throw new Error(errorBody?.error?.message || errorBody?.detail || `خطای سرور: ${res.status}`)
      }

      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      const assistantId = generateId()
      setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '' }])

      // Throttles setMessages to ~once/frame instead of once per SSE token
      // (see useStreamAccumulator.ts). accumulator.getText() replaces the
      // old plain `acc` string as the source of truth.
      const accumulator = new StreamAccumulator((text) => {
        setMessages(prev => {
          const copy = [...prev]
          const idx = copy.findIndex(m => m.id === assistantId)
          if (idx >= 0) copy[idx] = { ...copy[idx], content: text }
          return copy
        })
      })
      streamAccumulator = accumulator
      let usageData: { prompt_tokens?: number; completion_tokens?: number } | null = null
      // Captured from choices[0].finish_reason on whichever SSE chunk carries
      // it (null on every delta chunk until the last one; verified live
      // against the prod API container -- sanjab/gemini-3-flash returns
      // "length" on max_tokens, not "max_tokens"). Attached to the message
      // after the stream completes so finishReason.ts can decide whether the
      // response was cut off by the length ceiling.
      let capturedFinishReason: string | null = null
      // Carry-over buffer: a `data: {...}` line can split across two
      // reader.read() calls behind the Docker/Caddy proxy. Accumulate, split
      // on \n, keep the last (possibly incomplete) segment for the next read,
      // flush on stream end -- without this, a split line JSON.parse-fails and
      // is silently lost (and an error event with it).
      let sseBuffer = ''

      // Returns true when the stream must stop (upstream error event).
      const processLine = (rawLine: string): boolean => {
        const trimmed = rawLine.trim()
        if (!trimmed || !trimmed.startsWith('data:')) return false
        const data = trimmed.slice(5).trim()
        if (data === '[DONE]') return false
        let obj: any
        try { obj = JSON.parse(data) } catch { return false /* partial/non-JSON */ }
        // ── upstream error event ── backend emits `data: {"error": ...}` on
        // failure (two shapes; one leaks a raw Python exception string). Never
        // render that to the user: log the detail, show a generic Persian line
        // in the assistant bubble (keeping any partial text), and stop.
        if (obj.error) {
          console.error('chat stream upstream error:', obj.error, obj.code ?? '')
          // chat_stream.py's _sse_error_event emits {error:{code,message}} with
          // a message that is always a safe Persian string — prefer it so the
          // user sees the specific cause. A bare-string `error` is the older
          // shape and may carry a raw exception, so it never reaches the UI.
          const fromBackend = typeof obj.error?.message === 'string' ? obj.error.message : ''
          const errText = fromBackend || 'دریافت پاسخ از سرویس با خطا مواجه شد. لطفاً دوباره تلاش کنید.'
          // Cancel any pending throttled flush -- it would otherwise fire
          // after this and overwrite the error text.
          accumulator.cancel()
          const accText = accumulator.getText()
          setMessages(prev => {
            const copy = [...prev]
            const idx = copy.findIndex(m => m.id === assistantId)
            if (idx >= 0) copy[idx] = { ...copy[idx], content: accText ? `${accText}\n\n${errText}` : errText }
            return copy
          })
          return true
        }
        const delta = obj.choices?.[0]?.delta?.content
        if (delta) {
          accumulator.push(delta)
        }
        const finishReason = obj.choices?.[0]?.finish_reason
        if (typeof finishReason === 'string') capturedFinishReason = finishReason
        if (obj.usage) usageData = obj.usage
        if (obj.x_smart_model) setSmartModel(obj.x_smart_model)
        // ── billing event (real IRT cost) ──
        if (obj.type === 'billing') {
          // Wallet balance changed -- reflect the authoritative post-charge
          // amount the event carries (raw toman); refetch if it is absent.
          if (typeof obj.balance_after === 'number') {
            setWalletBalance(obj.balance_after)
          } else if (token) {
            fetch('/api/wallet', { headers: { Authorization: `Bearer ${token}` } })
              .then(r => r.ok ? r.json() : Promise.reject())
              .then(d => setWalletBalance(d.balance ?? 0))
              .catch(() => { /* silent */ })
          }
          setUsageStats(prev => ({
            promptTokens: obj.input_tokens ?? prev.promptTokens,
            completionTokens: obj.output_tokens ?? prev.completionTokens,
            totalTokens: (obj.input_tokens ?? 0) + (obj.output_tokens ?? 0),
            estimatedCost: obj.cost ?? prev.estimatedCost
          }))
        }
        // ── smart_info event ──
        if (obj.type === 'smart_info') {
          setSmartModel(obj.model)
        }
        // ── tokens/sec ──
        if (streamStartTimeRef.current > 0) {
          const elapsed = (Date.now() - streamStartTimeRef.current) / 1000
          const tps = usageData
            ? Math.round(((usageData.prompt_tokens ?? 0) + (usageData.completion_tokens ?? 0)) / Math.max(elapsed, 0.1))
            : 0
          setTokensPerSec(tps)
        }
        return false
      }

      let errored = false
      while (true) {
        const { value, done } = await reader!.read()
        if (done) break
        sseBuffer += decoder.decode(value, { stream: true })
        const lines = sseBuffer.split('\n')
        sseBuffer = lines.pop() ?? ''
        for (const line of lines) {
          if (processLine(line)) { errored = true; break }
        }
        if (errored) break
      }
      // Flush a trailing complete line the buffer still holds at stream end.
      if (!errored && sseBuffer.trim()) { if (processLine(sseBuffer)) errored = true }
      // On an upstream error, stop reading the (now-defunct) body cleanly.
      // (The error branch above already set the final bubble content and
      // cancelled the throttle, so it must not be flushed again here.)
      if (errored) {
        try { await reader!.cancel() } catch { /* already closed */ }
      } else {
        // Mandatory final flush -- the last tokens may postdate the last
        // scheduled throttled flush and must still reach the UI.
        accumulator.flushNow()
        // Record whatever finish_reason the stream carried (or null if it
        // never sent one) so ChatMessageItem can show the "ناتمام ماند" /
        // "بدون تولید متن" bar. Runs after flushNow() so this update merges
        // onto the message's final content rather than racing it.
        setMessages(prev => {
          const copy = [...prev]
          const idx = copy.findIndex(m => m.id === assistantId)
          if (idx >= 0) copy[idx] = { ...copy[idx], finishReason: capturedFinishReason }
          return copy
        })
      }

      // Auto-save after streaming completes
      if (convId) {
        const finalMsgs = [...updated, { id: assistantId, role: 'assistant' as const, content: accumulator.getText() }]
        saveMessages(convId, finalMsgs)
      }
      // Update token counts from usageData (cost comes from billing events).
      // usageData is now assigned inside the processLine closure above, which
      // defeats TS control-flow narrowing (it stays typed as its `null`
      // initializer here) -- the cast restores the real declared type.
      const finalUsage = usageData as { prompt_tokens?: number; completion_tokens?: number } | null
      if (finalUsage) {
        const promptTokens = finalUsage.prompt_tokens || 0
        const completionTokens = finalUsage.completion_tokens || 0
        const totalTokens = promptTokens + completionTokens
        setUsageStats(prev => ({
          promptTokens: prev.promptTokens + promptTokens,
          completionTokens: prev.completionTokens + completionTokens,
          totalTokens: prev.totalTokens + totalTokens,
          estimatedCost: prev.estimatedCost, // cost comes from billing events
        }))
      }
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'خطا در ارتباط'
      if (err instanceof Error && err.name === 'AbortError') {
        // Flush pending throttled tokens first, or the check below could
        // see a stale empty `last.content` and wrongly stamp "تولید متوقف
        // شد." over a response that had already started arriving.
        streamAccumulator?.flushNow()
        setMessages(prev => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          if (last?.role === 'assistant' && !last.content.trim()) {
            copy[copy.length - 1] = { ...last, content: 'تولید متوقف شد.' }
          }
          return copy
        })
      } else {
        setError(errMsg)
      }
      // Save partial progress even on error
      if (convId) {
        saveMessages(convId, messagesRef.current)
      }
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }, [messages, model, models, token, smartMode, webSearch, setWebSearch, setModel, createConversation, saveMessages, attachedFile, setAttachedFile, activeAssistant, setMessages, setInput, setShowPresets, setSmartModel, setWalletBalance, messagesRef, activeConversationIdRef, abortRef, setStreaming, setError, setUsageStats, setTokensPerSec, setSearchHintFor])

  // Keep ref in sync so retry() can call sendMessage without circular deps
  useEffect(() => { sendMessageRef.current = sendMessage }, [sendMessage])

  const retry = useCallback(async (msgIndex: number) => {
    if (!model) return
    const userMsg = messages.slice(0, msgIndex).filter(m => m.role === 'user').pop()
    if (!userMsg) return
    const newMsgs = messages.slice(0, msgIndex)
    setMessages(newMsgs)
    setError('')
    if (sendMessageRef.current) await sendMessageRef.current(userMsg.content, newMsgs)
  }, [messages, model, setMessages, setError])

  // "ادامه بده" button on a length-capped reply. Deliberately reuses the
  // normal sendMessage codepath (no bespoke "continue" request/endpoint):
  // it appends a plain user turn asking the model to continue, using the
  // full current transcript -- including the truncated reply itself -- as
  // context, exactly like any other follow-up message.
  const handleContinue = useCallback(() => {
    if (sendMessageRef.current) sendMessageRef.current('ادامه بده')
  }, [])

  // Explicit user action from the search-intent hint: drop the non-search
  // turn and re-send the same question with web search forced on.
  const handleResendWithSearch = useCallback(() => {
    if (!searchHintFor) return
    const { userMsgId, content } = searchHintFor
    const idx = messages.findIndex(m => m.id === userMsgId)
    setSearchHintFor(null)
    if (idx === -1) return
    const newMsgs = messages.slice(0, idx)
    setMessages(newMsgs)
    sendMessage(content, newMsgs, true)
  }, [searchHintFor, messages, sendMessage, setMessages])

  return {
    sendMessage,
    retry,
    handleContinue,
    handleResendWithSearch,
    cancel,
  }
}
